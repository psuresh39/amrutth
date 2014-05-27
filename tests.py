__author__ = 'user'

import unittest
from tornado.testing import AsyncHTTPTestCase
from tornado import web
from tornado import gen, ioloop
from foodtruckapi import NearbyFoodTruckHandler, FoodTruckInfoHandler


class MyHTTPTest(AsyncHTTPTestCase):
    def get_app(self):
        application = web.Application([
        (r"/searchfood", NearbyFoodTruckHandler),
        (r"/foodtruck", FoodTruckInfoHandler),
    ])
        return application

    def test_homepage(self):
        # The following two lines are equivalent to
        #   response = self.fetch('/')
        # but are shown in full here to demonstrate explicit use
        # of self.stop and self.wait.
        self.http_client.fetch(self.get_url('/foodtruck?name=Mexican'), self.stop)
        response = self.wait()
        # test contents of response
        print((type(response)))
        print(response)
