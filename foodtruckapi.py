import re
import ConfigParser
import json
import redis
from pymongo import MongoClient
from geopy.geocoders import GoogleV3
from geopy.distance import vincenty
from geoip import geolite2
from copy import copy
from exceptions import MissingParameterError,InternalServerError, InvalidParameterError


class FoodTrucks(object):
    def __init__(self, config_file='amrutth_settings.ini'):
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
        if self.query_parameter["limit"] > self.query_parameter["maxlimit"]:
                self.query_parameter["limit"] = self.query_parameter["maxlimit"]

    def create_multidict(self, *args):
        if len(args) == 1:
            return copy(args[0])
        out = {}
        for x in args[0]:
            out[x] = self.create_multidict(*args[1:])
        return out

    def get_cache(self):
        result = self.cache.get(self.query_parameter)
        return result

    def put_cache(self, result):
        self.cache.put(self.query_parameter, result)

class NearbyFoodTruckHandler(FoodTrucks):

    def __init__(self):
        super(NearbyFoodTruckHandler, self).__init__()

    def get_correct_sort_order(self, geo_query_result):

        offset_query_result = list(geo_query_result[self.query_parameter["offset"]:])
        result = []
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
        basic_bounds_query = self.create_multidict(['loc'], ['$geowithin'], ['$box'],
                                                   [[longitude[0], latitude[0]], [longitude[1], latitude[1]]])
        return basic_bounds_query

    def get_location_coordinates(self):
        if self.query_parameter["location"]:
            if self.query_parameter["location"] == "current":
                match = geolite2.lookup("127.0.0.1")
                try:
                    latitude, longitude = match.location
                except Exception as e:
                    print("Exception occured while guessing users ip address ", e)
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
        try:
            latitude, longitude = self.get_location_coordinates()
        except Exception:
            raise InvalidParameterError("Unable to find location")
        try:
            query = self.generate_basic_bounds_query(latitude, longitude)
            if self.query_parameter['category_filter']:
                query['facilitytype'] = self.query_parameter['category_filter']

            if self.query_parameter['status']:
                query['status'] = self.query_parameter['status']
        except Exception:
            raise InternalServerError("Error generating query")

        try:
            geo_query_result = self.foodtrucks.find(query).limit(self.query_parameter["limit"])
        except Exception:
            raise InternalServerError("Error querying database")
        else:
            return geo_query_result

    def generate_radius_query(self, latitude, longitude):
        return self.create_multidict(["loc"], ["$geoWithin"], ["$centerSphere"],
                                     [[longitude, latitude], self.query_parameter["radius_filter"] / 3959])

    def generate_distance_query(self, latitude, longitude):
        loc_query = self.create_multidict(["loc"], ["$near"], [longitude, latitude])
        distance_query = self.create_multidict(["$maxDistance"], self.query_parameter["max_distance"]/69)
        for key, value in distance_query.iteritems():
            loc_query[key] = value

        return loc_query

    def get_trucks_near_point(self):
        try:
            latitude, longitude = self.get_location_coordinates()
        except Exception:
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
        except:
            raise InternalServerError("Error generating query")

        try:
            geo_query_result = self.foodtrucks.find(query).limit(self.query_parameter["limit"])
        except:
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
            raise InternalServerError("Error performing sorting operation")
        return sorted_result

    def search_food_truck(self):
        result = self.get_cache()
        if result:
            return result
        else:
            if self.query_parameter["location"] and self.query_parameter["bounds"] and self.query_parameter["point"]:
                self.query_parameter["location"] = "current"
            elif ((self.query_parameter["location"] and self.query_parameter["bounds"]) or
                  (self.query_parameter["location"] and self.query_parameter["point"]) or
                  (self.query_parameter["point"] and self.query_parameter["location"]) or
                  (self.query_parameter["location"] and self.query_parameter["bounds"] and self.query_parameter["point"])):
                raise MissingParameterError("location field is missing in query")
            else:
                self.adjust_limit()
                try:
                    result = self.get_all_nearby_foodtrucks()
                except Exception:
                    raise
                else:
                    self.put_cache(json.dumps(result))
                    return json.dumps(result)


class FoodTruckInfoHandler(FoodTrucks):

    def __init__(self):
        super(FoodTruckInfoHandler, self).__init__()

    def generate_basic_query(self):
        return self.create_multidict(["$text"], ["$search"], self.query_parameter["name"])

    def generate_sort_query(self):
        return self.create_multidict(["score"], ["$meta"], "textScore")

    def get_foodtruck_info(self):
        try:
            query = self.generate_basic_query()
            sort_query = self.generate_sort_query()
            for key, value in sort_query.iteritems():
                query[key] = value
        except Exception:
            raise InternalServerError("Error generating query")

        try:
            result = self.foodtrucks.find(query).sort(sort_query).limit(self.query_parameter["limit"])
        except Exception:
            raise InternalServerError("Error querying database")
        else:
            return result

    def get_individual_foodtruck(self):
        result = self.get_cache()
        if result:
            return result
        else:
            if not self.query_parameter["name"]:
                raise MissingParameterError("name field is missing in query")
            else:
                self.adjust_limit()
                try:
                    result = self.get_foodtruck_info()
                except Exception:
                    raise
                else:
                    self.put_cache(json.dumps(result))
                    return json.dumps(result)

    def authhandler(self):
        pass

    def generalapilists(self):
        pass

    def syncdatabase(self):
        pass

if __name__ == "__main__":
    pass
