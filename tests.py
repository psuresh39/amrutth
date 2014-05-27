from tornado.testing import AsyncHTTPTestCase
from tornado import web
from foodtruckapi import NearbyFoodTruckHandler, FoodTruckInfoHandler
import json
import re
import time

search_name_pattern = re.compile("cupcake", re.I)

class MyHTTPTest(AsyncHTTPTestCase):
    def get_app(self):
        application = web.Application([
        (r"/searchfood", NearbyFoodTruckHandler),
        (r"/foodtruck", FoodTruckInfoHandler),
    ])
        return application

    def test_individual_foodtruck(self):
        self.http_client.fetch(self.get_url('/foodtruck?name=cupcake'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        for id, foodtruck in enumerate(json_response["response"]["text"][1]):
            if not search_name_pattern.search(foodtruck["applicant"]):
                self.fail("Applicant name does not match requested name")

    def test_individual_missingparam(self):
        self.http_client.fetch(self.get_url('/foodtruck'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["error"]["text"][0], 1001)

    def test_cache(self):
        rand = time.time()
        cache_miss_pattern = "cache miss. Key={'sort': 0, 'status': None, 'name': 'cupcake"+str(rand)+"'.*"
        cache_hit_pattern = "cache hit. Key={'sort': 0, 'status': None, 'name': 'cupcake"+str(rand)+"'.*"
        self.http_client.fetch(self.get_url('/foodtruck?name=cupcake'+str(rand)), self.stop)
        response = self.wait()
        self.http_client.fetch(self.get_url('/foodtruck?name=cupcake'+str(rand)), self.stop)
        response = self.wait()
        with open("log", "r") as f:
            log_data = f.read()
        if not re.search(cache_miss_pattern, log_data) or not re.search(cache_hit_pattern, log_data):
            self.fail("Cache miss and a hit expected for query pattern")

    def test_limit(self):
        self.http_client.fetch(self.get_url('/searchfood?location=2%20Clinton%20Park%20San%20Francisco&limit=200'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        self.assertTrue(len(json_response["response"]["text"][1]) <= 100)

    def test_radius_query(self):
        self.http_client.fetch(self.get_url('/searchfood?location=2%20Clinton%20Park%20San%20Francisco&radius_filter=5&category_filter=Truck&status=APPROVED'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        for id, foodtruck in enumerate(json_response["response"]["text"][1]):
            if not re.search("Truck", foodtruck["facilitytype"]) or not re.search("APPROVED", foodtruck["status"]):
                self.fail("Result does not match query")

    def test_distance_query(self):
        self.http_client.fetch(self.get_url('/searchfood?location=2%20Clinton%20Park%20San%20Francisco&category_filter=Truck&status=APPROVED'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        for id, foodtruck in enumerate(json_response["response"]["text"][1]):
                if not re.search("Truck", foodtruck["facilitytype"]) or not re.search("APPROVED", foodtruck["status"]):
                        self.fail("Result does not match query")

    def test_bounds_query(self):
        self.http_client.fetch(self.get_url('/searchfood?bounds=37.777863,-122.426549|37.790743,-122.404351&category_filter=Truck&status=APPROVED'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        for id, foodtruck in enumerate(json_response["response"]["text"][1]):
                if not re.search("Truck", foodtruck["facilitytype"]) or not re.search("APPROVED", foodtruck["status"]):
                        self.fail("Result does not match query")

    def test_point_query(self):
        self.http_client.fetch(self.get_url('/searchfood?point=37.777863,-122.426549&category_filter=Truck&status=APPROVED'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)

    def test_filter_sort_offset(self):
        self.http_client.fetch(self.get_url('/searchfood?location=2%20Clinton%20Park%20San%20Francisco&limit=10&offset=6'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        self.assertEqual(len(json_response["response"]["text"][1]), 4)

    def test_filter_sort_distance(self):
        self.http_client.fetch(self.get_url('/searchfood?point=37.777863,-122.426549'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        sorted_list = sorted(json_response["response"]["text"][1], key=lambda x:x["dis"])
        self.assertEqual(sorted_list, json_response["response"]["text"][1])

    def test_sort_filter_name(self):
        name_pattern = re.compile("Mexican.*", re.I)
        fooditem_pattern = re.compile("Taco.*", re.I)
        self.http_client.fetch(self.get_url('/searchfood?point=37.777863,-122.426549&name=mexican&fooditems=taco'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        for id, foodtruck in enumerate(json_response["response"]["text"][1]):
                    if not name_pattern.search(foodtruck["applicant"]) or not fooditem_pattern.search(foodtruck["fooditems"]):
                            self.fail("Result does not match query")

    def test_name_based_sorting(self):
        self.http_client.fetch(self.get_url('/searchfood?point=37.777863,-122.426549&name=mexican&fooditems=taco'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["response"]["text"][0], 0)
        sorted_list = sorted(json_response["response"]["text"][1], key=lambda x:x["applicant"])
        self.assertEqual("sorted_list", json_response["response"]["text"][1])

    def test_wrong_bounds_query(self):
        self.http_client.fetch(self.get_url('/searchfood?bounds=&category_filter=Truck&status=APPROVED'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["error"]["text"][0], 1002)

    def test_wrong_location_query(self):
        self.http_client.fetch(self.get_url('/searchfood?point=&category_filter=Truck&status=APPROVED'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["error"]["text"][0], 1002)

    def test_ambiguous_location_query(self):
        self.http_client.fetch(self.get_url('/searchfood?point=37.777863,-122.426549&location=2%20Clinton%20Park%20San%20Francisco&name=mexican&fooditems=taco'), self.stop)
        response = self.wait()
        json_response = json.loads(response.body)
        self.assertEqual(json_response["error"]["text"][0], 1002)
