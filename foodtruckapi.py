import re
import ConfigParser
import json
import redis
import argparse
import urlparse
import logging
from pymongo import MongoClient
from geopy.geocoders import GoogleV3
from geopy.distance import vincenty
from geoip import geolite2
from copy import copy
from exceptions import MissingParameterError, InternalServerError, InvalidParameterError
import tornado.web
import tornado.httpserver
import tornado.ioloop

log = logging.getLogger("food_truck_logger")
log.setLevel(logging.WARNING)
log.propagate = False

ch = log.StreamHandler()
ch.setLevel(logging.DEBUG)
log.addHandler(ch)

fh = log.handlers.RotatingFileHandler("log", maxBytes=1024*1024, backupCount=10)
fh.setLevel(logging.DEBUG)
log.addHandler(fh)

class FoodTrucks(object):
    SUCCESS = 0

    def __init__(self, config_file='amrutth_settings.ini'):
        log.debug("[FoodTrucks] Initializing")
        self.client = MongoClient()
        self.db = self.client.test
        self.foodtrucks = self.db.foodtrucks
        self.geolocator = GoogleV3()
        self._config_file = config_file
        self._config = ConfigParser.RawConfigParser()
        self.query_parameter = {}
        self.cache = redis.StrictRedis(host='localhost', port=6379, db=0)
        if not self._config.read(self._config_file):
            self._config.add_section('Query Options')
            self._config.set('Query Options', 'location', json.dumps(None))
            self._config.set('Query Options', 'bounds', json.dumps(None))
            self._config.set('Query Options', 'point', json.dumps(None))
            self._config.set('Query Options', 'limit', json.dumps(40))
            self._config.set('Query Options', 'maxlimit', json.dumps(100))
            self._config.set('Query Options', 'offset', json.dumps(0))
            self._config.set('Query Options', 'sort', json.dumps(0))
            self._config.set('Query Options', 'category_filter', json.dumps(None))
            self._config.set('Query Options', 'radius_filter', json.dumps(None))
            self._config.set('Query Options', 'max_distance', json.dumps(10))
            self._config.set('Query Options', 'name', json.dumps(None))
            self._config.set('Query Options', 'status', json.dumps(None))
            self._config.set('Query Options', 'fooditems', json.dumps(None))
            with open(self._config_file, 'w') as configfile:
                configfile.write(self._config_file)

        if self._config.has_section('Query Option'):
            self.query_parameter = {option: json.loads(self._config.get("Query Option", option))
                                    for option in self._config.options('Query Options')}

    def adjust_limit(self):
        log.debug("[FoodTrucks] Adjusting limit")
        if self.query_parameter["limit"] > self.query_parameter["maxlimit"]:
                self.query_parameter["limit"] = self.query_parameter["maxlimit"]

    def create_multidict(self, *args):
        log.debug("[FoodTrucks] Creating query string")
        if len(args) == 1:
            return copy(args[0])
        out = {}
        for x in args[0]:
            out[x] = self.create_multidict(*args[1:])
        return out

    def generate_error(self, e):
        log.debug("[FoodTrucks] Generating json error")
        err = self.create_multidict(['error'], ['text'], [e.code, e.msg])
        return json.dumps(err)

    def generate_response(self, result):
        log.debug("[FoodTrucks] Generating json response")
        res = self.create_multidict(['response', ['text'], [self.SUCCESS, result]])
        return json.dumps(res)

    def get_cache(self):
        log.debug("[FoodTrucks] Checking for key in cache", self.query_parameter)
        result = self.cache.get(self.query_parameter)
        return result

    def put_cache(self, result):
        log.debug("[FoodTrucks] Putting key in cache", self.query_parameter)
        self.cache.set(self.query_parameter, result)


class NearbyFoodTruckHandler(FoodTrucks, tornado.web.RequestHandler):

    def __init__(self):
        self.debug("[NearbyFoodTruckHandler] Initializing")
        super(NearbyFoodTruckHandler, self).__init__()

    def get_correct_sort_order(self, geo_query_result):
        self.debug("[NearbyFoodTruckHandler] Getting correct sort order for result")
        offset_query_result = list(geo_query_result[self.query_parameter["offset"]:])
        if not self.query_parameter["name"] and not self.query_parameter["fooditems"]:
                result = offset_query_result
        else:
            applicant = self.query_parameter["name"] or ".*"
            fooditems = self.query_parameter["fooditems"] or ".*"
            result = [foodtruck for foodtruck in offset_query_result
                      if re.search(fooditems, foodtruck["fooditems"]) and re.search(applicant, foodtruck["applicant"])]

            if self.query_parameter["sort"] == 1:
                if self.query_parameter["name"]:
                    result = sorted(result, key=lambda x: x["applicant"])
                else:
                    result = sorted(result, key=lambda x: x["fooditems"])

        for index, foodtruck in enumerate(result[:]):
            result[index]["dis"] = vincenty((self.query_parameter["latitude"], self.query_parameter["longitude"]),
                                            (result[index]["latitude"], result[index]["longitude"])).miles
        return result

    def generate_basic_bounds_query(self, latitude, longitude):
        log.debug("[NearbyFoodTruckHandler] Generate basic bounds query")
        basic_bounds_query = self.create_multidict(['loc'], ['$geowithin'], ['$box'],
                                                   [[longitude[0], latitude[0]], [longitude[1], latitude[1]]])
        return basic_bounds_query

    def get_location_coordinates(self):
        log.debug("[NearbyFoodTruckHandler] Get location coordinates")
        if self.query_parameter["location"]:
            if self.query_parameter["location"] == "current":
                match = geolite2.lookup("127.0.0.1")
                latitude, longitude = match.location
            else:
                address, (latitude, longitude) = self.geolocator.geocode(self.query_parameter["location"])
        elif self.query_parameter["point"]:
            coordinates = self.query_parameter["point"].split(",")
            latitude = float(coordinates[0])
            longitude = float(coordinates[1])
        else:
            latitude = {}
            longitude = {}
            for idx, coordinate in enumerate(self.query_parameter["bounds"].split("|")):
                latlang = coordinate.split(",")
                latitude[idx] = float(latlang[0])
                longitude[idx] = float(latlang[1])

        return latitude, longitude

    def get_trucks_within_box(self):
        log.debug("[NearbyFoodTruckHandler] Search within bounded box")
        try:
            latitude, longitude = self.get_location_coordinates()
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Unable to find coordinates", e)
            raise InvalidParameterError("Unable to find location")
        try:
            query = self.generate_basic_bounds_query(latitude, longitude)
            if self.query_parameter['category_filter']:
                query['facilitytype'] = self.query_parameter['category_filter']

            if self.query_parameter['status']:
                query['status'] = self.query_parameter['status']
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error generating query", e)
            raise InternalServerError("Error generating query")

        try:
            geo_query_result = self.foodtrucks.find(query).limit(self.query_parameter["limit"])
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error querying database", e)
            raise InternalServerError("Error querying database")
        else:
            return geo_query_result

    def generate_radius_query(self, latitude, longitude):
        log.debug("[NearbyFoodTruckHandler] Generate radius query")
        return self.create_multidict(["loc"], ["$geoWithin"], ["$centerSphere"],
                                     [[longitude, latitude], self.query_parameter["radius_filter"] / 3959])

    def generate_distance_query(self, latitude, longitude):
        log.debug("[NearbyFoodTruckHandler] Generate distance query")
        loc_query = self.create_multidict(["loc"], ["$near"], [longitude, latitude])
        distance_query = self.create_multidict(["$maxDistance"], self.query_parameter["max_distance"]/69)
        for key, value in distance_query.iteritems():
            loc_query[key] = value

        return loc_query

    def get_trucks_near_point(self):
        log.debug("[NearbyFoodTruckHandler] Search near a point")
        try:
            latitude, longitude = self.get_location_coordinates()
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Unable to find location", e)
            raise InvalidParameterError("Unable to find location")

        try:
            if self.query_parameter["radius_filter"]:
                query = self.generate_radius_query(latitude, longitude)
            else:
                query = self.generate_distance_query(latitude, longitude)

            if self.query_parameter["category_filter"]:
                query["facilitytype"] = self.query_parameter["category_filter"]
            if self.query_parameter["status"]:
                query["status"] = self.query_parameter["status"]
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error generating query", e)
            raise InternalServerError("Error generating query")

        try:
            geo_query_result = self.foodtrucks.find(query).limit(self.query_parameter["limit"])
        except:
            log.error("[NearbyFoodTruckHandler] Error querying DB")
            raise InternalServerError("Error querying database")
        else:
            return geo_query_result

    def get_all_nearby_foodtrucks(self):
        if self.query_parameter["bounds"]:
            try:
                geo_query_result = self.get_trucks_near_point()
            except Exception:
                raise
        else:
            try:
                geo_query_result = self.get_trucks_within_box()
            except Exception:
                raise
        try:
            sorted_result = self.get_correct_sort_order(geo_query_result)
        except Exception:
            log.error("[NearbyFoodTruckHandler] Error sorting results")
            raise InternalServerError("Error performing sorting operation")
        return sorted_result

    def search_food_truck(self):
        result = self.get_cache()
        if result:
            log.info("[NearbyFoodTruckHandler] Cache hit", self.query_parameter)
            return result
        else:
            log.info("[NearbyFoodTruckHandler] Cache miss", self.query_parameter)
            if self.query_parameter["location"] and self.query_parameter["bounds"] and self.query_parameter["point"]:
                self.query_parameter["location"] = "current"
            elif (
                    (self.query_parameter["location"] and self.query_parameter["bounds"])
                    or (self.query_parameter["location"] and self.query_parameter["point"])
                    or (self.query_parameter["point"] and self.query_parameter["location"])
                    or (self.query_parameter["location"] and self.query_parameter["bounds"]
                        and self.query_parameter["point"])
            ):
                log.warning("[NearbyFoodTruckHandler] location field missing")
                raise MissingParameterError("location field is missing in query")
            else:
                self.adjust_limit()
                try:
                    result = self.get_all_nearby_foodtrucks()
                except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
                    log.warning("[NearbyFoodTruckHandler] Error occurred processing request", e)
                    raise e
                except Exception as e:
                    log.error("[NearbyFoodTruckHandler] Unexpected error occurred", e)
                    raise InternalServerError
                else:
                    log.debug("[NearbyFoodTruckHandler] processed request, result received")
                    self.put_cache(result)
                    return result

    def get(self):
        url = urlparse.urlparse(self.request.uri)
        query = urlparse.parse_qs(url.query)
        for parameter, value in query.iteritems():
            self.query_parameter[parameter] = value

        try:
            result = self.search_food_truck()
        except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
            self.set_status(e.http_code)
            self.set_header('Content-type', 'application/json')
            error = self.generate_error(e)
            self.write(error)
        else:
            self.set_status(200)
            self.set_header('Content-type', 'application/json')
            response = self.generate_response(result)
            self.write(response)


class FoodTruckInfoHandler(FoodTrucks, tornado.web.RequestHandler):

    def __init__(self):
        log.debug("[FoodTruckInfoHandler] Initializing")
        super(FoodTruckInfoHandler, self).__init__()

    def generate_basic_query(self):
        return self.create_multidict(["$text"], ["$search"], self.query_parameter["name"])

    def generate_sort_query(self):
        return self.create_multidict(["score"], ["$meta"], "textScore")

    def get_foodtruck_info(self):
        try:
            log.debug("[FoodTruckInfoHandler] Generating query")
            query = self.generate_basic_query()
            sort_query = self.generate_sort_query()
            for key, value in sort_query.iteritems():
                query[key] = value
        except Exception:
            log.error("[FoodTruckInfoHandler] Error generating query")
            raise InternalServerError("Error generating query")

        try:
            log.debug("[FoodTruckInfoHandler] Perform DB query")
            result = self.foodtrucks.find(query).sort(sort_query).limit(self.query_parameter["limit"])
        except Exception:
            log.error("[FoodTruckInfoHandler] Error querying database")
            raise InternalServerError("Error querying database")
        else:
            return result

    def get_individual_foodtruck(self):
        result = self.get_cache()
        if result:
            log.info("[FoodTruckInfoHandler] cache hit", self.query_parameter)
            return result
        else:
            log.info("[FoodTruckInfoHandler] cache miss", self.query_parameter)
            if not self.query_parameter["name"]:
                log.warning("[FoodTruckInfoHandler] Got exception processing request", e)
                raise MissingParameterError("name field is missing in query")
            else:
                self.adjust_limit()
                try:
                    result = self.get_foodtruck_info()
                except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
                    log.warning("[FoodTruckInfoHandler] Got exception processing request", e)
                    raise e
                except Exception as e:
                    log.error("[FoodTruckInfoHandler] Unexpected error occurred", e)
                    raise InternalServerError
                else:
                    log.debug("[FoodTruckInfoHandler] processed request, result received")
                    self.put_cache(result)
                    return result

    def get(self):
        log.debug("[FoodTruckInfoHandler] Got request: ", self.request.uri)
        url = urlparse.urlparse(self.request.uri)
        query = urlparse.parse_qs(url.query)
        for parameter, value in query.iteritems():
            self.query_parameter[parameter] = value

        log.debug("[FoodTruckInfoHandler] The query parameters are: ", self.query_parameter)
        try:
            result = self.get_individual_foodtruck()
        except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
            log.warning("[FoodTruckInfoHandler] Got exception processing request", e)
            self.set_status(e.http_code)
            self.set_header('Content-type', 'application/json')
            error = self.generate_error(e)
            self.write(error)
        else:
            log.debug("[FoodTruckInfoHandler] request processed successfully")
            self.set_status(200)
            self.set_header('Content-type', 'spplicstion/json')
            response = self.generate_response(result)
            self.write(response)

    def authhandler(self):
        pass

    def generalapilists(self):
        pass

    def syncdatabase(self):
        pass

if __name__ == "__main__":
    bindport = 4545
    bindhost = "0.0.0.0"
    sslport = 4546
    sslhost = "0.0.0.0"
    parser = argparse.ArgumentParser()
    parser.add_argument("-http", help="host:port for http connections")
    parser.add_argument("-https", help="host:port for https connections")
    parser.add_argument("-loglevel", help="logging level for module", type=int)
    args = parser.parse_args()

    if args.loglevel:
        log.setLevel(args.loglevel)

    if args.http:
        bindhost, bindport = args.http.split(":")

    if args.https:
        sslhost, sslport = args.https.split(":")

    application = tornado.web.Application([
        (r"/search", NearbyFoodTruckHandler),
        (r"/foodtruck", FoodTruckInfoHandler)
    ])

    https_server = tornado.httpserver.HTTPServer(application, ssl_options={
        "certfile": "/var/foodtruck/keys/ca.csr",
        "keyfile": "/var/foodtruck/keys/ca.key",
    })

    http_server = tornado.httpserver.HTTPServer(application)

    log.info("Starting web application: http/https servers and ioloop")

    https_server.listen(sslhost, sslport)
    http_server.listen(bindhost, bindport)
    tornado.ioloop.IOLoop.instance().start()