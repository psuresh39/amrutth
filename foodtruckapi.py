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
from foodtruckexceptions import MissingParameterError, InternalServerError, InvalidParameterError
import tornado.web
import tornado.httpserver
import tornado.ioloop

log = logging.getLogger("food_truck_logger")
log.setLevel(logging.WARNING)
log.propagate = False

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
log.addHandler(ch)

fh = logging.handlers.RotatingFileHandler("log", maxBytes=1024*1024, backupCount=10)
fh.setLevel(logging.DEBUG)
log.addHandler(fh)


class FoodTrucks(tornado.web.RequestHandler):
    SUCCESS = 0

    def initialize(self, config_file="amrutth.settings.ini"):
        log.debug("[FoodTrucks] Initializing")
        self.client = MongoClient()
        self.db = self.client.test
        self.foodtrucks = self.db.foodtrucks
        self.latitude =  ""
        self.longitude = ""
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
            self._config.set('Query Options', 'name', json.dumps(None))
            self._config.set('Query Options', 'status', json.dumps(None))
            self._config.set('Query Options', 'fooditems', json.dumps(None))
            with open(self._config_file, 'w') as configfile:
                self._config.write(configfile)

        if self._config.has_section('Query Options'):
            self.query_parameter = {option: json.loads(self._config.get("Query Options", option))
                                    for option in self._config.options('Query Options')}

    def adjust_limit(self):
        log.debug("[FoodTrucks] Adjusting limit")
        if int(self.query_parameter["limit"]) > self.query_parameter["maxlimit"]:
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
        log.debug("[FoodTrucks] Checking for key {0} in cache".format(str(self.query_parameter)))
        try:
            query_key = [(key, value) for key, value in sorted(self.query_parameter.iteritems())]
            result = json.loads(self.cache.get(query_key))
        except Exception:
            return None
        else:
            return result

    def put_cache(self, result):
        log.debug("[FoodTrucks] Putting key {0} in cache".format(str(self.query_parameter)))
        query_key = [(key, value) for key, value in sorted(self.query_parameter.iteritems())]
        self.cache.set(query_key, json.dumps(result))


class NearbyFoodTruckHandler(FoodTrucks):

    def initialize(self):
        log.debug("[NearbyFoodTruckHandler] Initializing")
        super(NearbyFoodTruckHandler, self).initialize()

    def query_filter_sort(self, geo_query_result_list):
        log.debug("[NearbyFoodTruckHandler] Getting correct sort order for result")
        offset_query_result_list = geo_query_result_list[int(self.query_parameter["offset"]):]
        if not self.query_parameter["name"] and not self.query_parameter["fooditems"]:
                result_list = offset_query_result_list
        else:
            applicant = self.query_parameter["name"] or ".*"
            fooditems = self.query_parameter["fooditems"] or ".*"

            applicant_regex = re.compile(applicant, re.IGNORECASE)
            fooditems_regex = re.compile(fooditems, re.IGNORECASE)

            result_list = [foodtruck for foodtruck in offset_query_result_list
                           if re.search(fooditems_regex, foodtruck["fooditems"]) and
                           re.search(applicant_regex, foodtruck["applicant"])]

            if int(self.query_parameter["sort"]) == 1:
                if self.query_parameter["name"]:
                    result_list = sorted(result_list, key=lambda x: x["applicant"])
                else:
                    result_list = sorted(result_list, key=lambda x: x["fooditems"])

        if not self.query_parameter["bounds"]:
            for index, foodtruck in enumerate(result_list[:]):
                result_list[index]["dis"] = vincenty((self.latitude, self.longitude),
                                                 (result_list[index]["loc"][1], result_list[index]["loc"][0])).miles

        return result_list

    def get_location_coordinates(self):
        log.debug("[NearbyFoodTruckHandler] Get location coordinates")
        if self.query_parameter["location"]:
            if self.query_parameter["location"] == "current":
                match = geolite2.lookup(self.request.remote_ip)
                latitude, longitude = match.location
                return float(latitude), float(longitude)
            else:
                address, (latitude, longitude) = self.geolocator.geocode(self.query_parameter["location"])
                return float(latitude), float(longitude)
        elif self.query_parameter["point"]:
            coordinates = self.query_parameter["point"].split(",")
            latitude = coordinates[0]
            longitude = coordinates[1]
            return float(latitude), float(longitude)
        else:
            latitude = {}
            longitude = {}
            for idx, coordinate in enumerate(self.query_parameter["bounds"].split("|")):
                latlang = coordinate.split(",")
                latitude[idx] = float(latlang[0])
                longitude[idx] = float(latlang[1])
            return latitude, longitude

    def generate_basic_bounds_query(self, latitude, longitude):
        log.debug("[NearbyFoodTruckHandler] Generate basic bounds query")
        basic_bounds_query = self.create_multidict(['loc'], ['$geowithin'], ['$box'],
                                                   [[longitude[0], latitude[0]], [longitude[1], latitude[1]]])
        return basic_bounds_query

    def get_trucks_within_box(self):
        log.debug("[NearbyFoodTruckHandler] Search within bounded box")
        try:
            latitude, longitude = self.get_location_coordinates()
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Unable to find coordinates: {0}".format(str(e)))
            raise InvalidParameterError("Unable to find location")
        try:
            query = self.generate_basic_bounds_query(latitude, longitude)
            if self.query_parameter['category_filter']:
                query['facilitytype'] = self.query_parameter['category_filter']

            if self.query_parameter['status']:
                query['status'] = self.query_parameter['status']
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error generating bounds query: {0}".format(str(e)))
            raise InternalServerError("Error generating query")

        try:
            geo_query_result = self.foodtrucks.find(query).limit(int(self.query_parameter["limit"]))
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error querying database: {0}".format(str(e)))
            raise InternalServerError("Error querying database")
        else:
            return list(geo_query_result)

    def generate_radius_query(self, latitude, longitude):
        log.debug("[NearbyFoodTruckHandler] Generate radius query")
        return self.create_multidict(["loc"], ["$geoWithin"], ["$centerSphere"],
                                     [[longitude, latitude], float(self.query_parameter["radius_filter"]) / 3959])

    def generate_distance_query(self, latitude, longitude):
        log.debug("[NearbyFoodTruckHandler] Generate distance query")
        return self.create_multidict(["loc"], ["$near"], [longitude, latitude])

    def get_trucks_near_point(self):
        log.debug("[NearbyFoodTruckHandler] Search near a point")
        try:
            latitude, longitude = self.get_location_coordinates()
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Unable to find location: {0}".format(str(e)))
            raise InvalidParameterError("Unable to find location")

        self.latitude = latitude
        self.longitude = longitude

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
            log.error("[NearbyFoodTruckHandler] Error generating near point query: {0}".format(str(e)))
            raise e

        try:
            geo_query_result = self.foodtrucks.find(query).limit(int(self.query_parameter["limit"]))
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error querying DB for near point query {0}".format(str(e)))
            raise InternalServerError("Error querying database")
        else:
            return list(geo_query_result)

    def get_all_nearby_foodtrucks(self):
        if not self.query_parameter["bounds"]:
            try:
                geo_query_result_list = self.get_trucks_near_point()
            except Exception as e:
                log.error("[NearbyFoodTruckHandler] Error getting results for point/loc: {}".format(str(e)))
                raise e
        else:
            try:
                geo_query_result_list = self.get_trucks_within_box()
            except Exception as e:
                log.error("[NearbyFoodTruckHandler] Error getting results for box: {}".format(str(e)))
                raise e
        try:
            sorted_result_list = self.query_filter_sort(geo_query_result_list)
        except Exception as e:
            log.error("[NearbyFoodTruckHandler] Error sorting results: {}".format(str(e)))
            return geo_query_result_list
        else:
            return sorted_result_list

    def search_food_truck(self):
        if (
            (self.query_parameter["location"] and self.query_parameter["bounds"])
            or (self.query_parameter["location"] and self.query_parameter["point"])
            or (self.query_parameter["point"] and self.query_parameter["location"])
            or (self.query_parameter["location"] and self.query_parameter["bounds"]
                and self.query_parameter["point"])
        ):
                log.warning("[NearbyFoodTruckHandler] Invalid query parameters")
                raise InvalidParameterError("multiple locations specified, cannot disambiguate")
        else:
            resultlist = self.get_cache()
            if resultlist:
                log.info("[NearbyFoodTruckHandler] Cache hit. Key={0}".format(str(self.query_parameter)))
                return resultlist
            else:
                log.info("[NearbyFoodTruckHandler] Cache miss. Key={0}".format(str(self.query_parameter)))
                if not self.query_parameter["location"] and not self.query_parameter["bounds"]\
                        and not self.query_parameter["point"]:
                    self.query_parameter["location"] = "current"

                self.adjust_limit()
                try:
                    resultlist = self.get_all_nearby_foodtrucks()
                except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
                    log.warning("[NearbyFoodTruckHandler] Error occurred processing request: {0}".format(str(e)))
                    raise e
                except Exception as e:
                    log.error("[NearbyFoodTruckHandler] Unexpected error occurred: {0}".format(str(e)))
                    raise InternalServerError("Unexpected internal server error")
                else:
                    log.debug("[NearbyFoodTruckHandler] processed request, result received")
                    for key, value in enumerate(resultlist[:]):
                        resultlist[key]["_id"] = key
                    self.put_cache(resultlist)
                    return resultlist

    def get(self):
        log.debug("[NearbyFoodTruckHandler] Got request: {0} ".format(str(self.request.uri)))
        url = urlparse.urlparse(self.request.uri)
        query = urlparse.parse_qs(url.query)
        for parameter, value in query.iteritems():
            self.query_parameter[parameter] = value[0]

        try:
            resultlist = self.search_food_truck()
        except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
            self.set_status(e.http_code)
            self.set_header('Content-type', 'application/json')
            error = self.generate_error(e)
            self.write(error)
        else:
            self.set_status(200)
            self.set_header('Content-type', 'application/json')
            response = self.generate_response(resultlist)
            self.write(response)


class FoodTruckInfoHandler(FoodTrucks):

    def initialize(self):
        log.debug("[FoodTruckInfoHandler] Initializing")
        super(FoodTruckInfoHandler, self).initialize()

    def query_database(self):
        res = self.foodtrucks.find(
            {"$text": {"$search": self.query_parameter["name"]}}, {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(int(self.query_parameter["limit"]))
        return res

    def get_foodtruck_info(self):
        try:
            log.debug("[FoodTruckInfoHandler] Perform DB query")
            result = self.query_database()
        except Exception as e:
            log.error("[FoodTruckInfoHandler] Error querying database: {0}".format(str(e)))
            raise InternalServerError("Error querying database")
        else:
            return list(result)

    def get_individual_foodtruck(self):
        if not self.query_parameter["name"]:
            raise MissingParameterError("name field is missing in query")
        else:
            resultlist = self.get_cache()
            if resultlist:
                log.info("[FoodTruckInfoHandler] cache hit. Key={0}".format(str(self.query_parameter)))
                return resultlist
            else:
                log.info("[FoodTruckInfoHandler] cache miss. Key={0}".format(str(self.query_parameter)))
                self.adjust_limit()
                try:
                    result = self.get_foodtruck_info()
                except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
                    log.warning("[FoodTruckInfoHandler] Got exception processing request: {0}".format(str(e)))
                    raise e
                except Exception as e:
                    log.error("[FoodTruckInfoHandler] Unexpected error occurred: {0}".format(str(e)))
                    raise InternalServerError("Unexpected internal server error")
                else:
                    log.debug("[FoodTruckInfoHandler] processed request, result received")
                    resultlist = []
                    for key, value in enumerate(result):
                        value["_id"] = key
                        resultlist.append(value)
                    self.put_cache(resultlist)
                    return resultlist

    def get(self):
        log.debug("[FoodTruckInfoHandler] Got request: {0} ".format(str(self.request.uri)))
        url = urlparse.urlparse(self.request.uri)
        query = urlparse.parse_qs(url.query)
        for parameter, value in query.iteritems():
            self.query_parameter[parameter] = value[0]

        log.debug("[FoodTruckInfoHandler] The query parameters are: {0}".format(str(self.query_parameter)))
        try:
            resultlist = self.get_individual_foodtruck()
        except (InternalServerError, InvalidParameterError, MissingParameterError) as e:
            log.warning("[FoodTruckInfoHandler] Got exception processing request: {0}".format(str(e)))
            self.set_status(e.http_code)
            self.set_header('Content-type', 'text/plain')
            error = self.generate_error(e)
            self.write(error)
        else:
            log.debug("[FoodTruckInfoHandler] request processed successfully")
            self.set_status(200)
            self.set_header('Content-type', 'text/plain')
            response = self.generate_response(resultlist)
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
        (r"/searchfood", NearbyFoodTruckHandler),
        (r"/foodtruck", FoodTruckInfoHandler),
    ])

    https_server = tornado.httpserver.HTTPServer(application, ssl_options={
        "certfile": "/etc/ssl/localcerts/tornado.pem",
        "keyfile": "/etc/ssl/localcerts/tornado.key",
    })

    http_server = tornado.httpserver.HTTPServer(application)

    log.info("Starting web application: http/https servers and ioloop")

    https_server.listen(sslport, sslhost)
    http_server.listen(bindport, bindhost)
    tornado.ioloop.IOLoop.instance().start()
