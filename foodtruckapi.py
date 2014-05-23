import json
from pymongo import MongoClient
from geopy.geocoders import GoogleV3
from geopy.distance import vincenty
from geoip import geolite2
import re

def authhandler():
    pass

def getfoodtrucks(latitude, longitude, limit, offset, sort, category_filter, radius_filter, max_distance, name, status, fooditems):



def searchfoodtruck(location=None, bounds=None, point=None , limit=40, offset=0, sort=0, category_filter=None, radius_filter=None, max_distance=10, name=None, status=None, fooditems=None):
    if location == None and bounds == None and point == None:
        location = "current"
    elif ((location and bounds) or (location and point) or (point and location) or (location and bounds and point)):
        print("Use only one of the location methods")
        return
    else:
        #Make mongoDB query
        client = MongoClient()
        db = client.test
        foodtrucks = db.foodtrucks
        geolocator = GoogleV3()
        if limit > 100:
            limit = 100
        if location not None:
            if location == current:
                match = geolite2.lookup("127.0.0.1")
                try:
                    latitude, longitude = match.location
                except Exception as e:
                    print("Exception occured while guessing users ip address ", e)
            else:
                address, (latitude, longitude) = geolocator.geocode(location)

        elif point not None:
            coordinates = point.split(",")
            latitude = float(coordinates[0])
            longitude = float(coordinates[1])

            if category_filter is None and status is None:

                if radius_filter is not None:
                    geo_query_result = foodtrucks.find({ "loc" : { "$geoWithin" :{ "$centerSphere" :[ [ longitude, latitude ] , radius_filter / 3959 ]} } } ).limit(limit)
                else:
                    geo_query_result = foodtrucks.find({ "loc" : { "$near" : [ longitude, latitude ] , $maxDistance: max_distance/69} } ).limit(limit)
            elif category_filter is not None and status is None:

                if radius_filter is not None:
                    geo_query_result = foodtrucks.find({ "loc" : { "$geoWithin" :{ "$centerSphere" :[ [ longitude, latitude ] , radius_filter / 3959 ]} } , "facilitytype":category_filter} ).limit(limit)
                else:
                    geo_query_result = foodtrucks.find({ "loc" : { "$near" : [ longitude, latitude ] , $maxDistance: max_distance/69}, "facilitytype":category_filter } ).limit(limit)
            elif category_filter is None and status is not None:

                if radius_filter is not None:
                    geo_query_result = foodtrucks.find({ "loc" : { "$geoWithin" :{ "$centerSphere" :[ [ longitude, latitude ] , radius_filter / 3959 ]} } , "status":status} ).limit(limit)
                else:
                    geo_query_result = foodtrucks.find({ "loc" : { "$near" : [ longitude, latitude ] , $maxDistance: max_distance/69}, "status":status } ).limit(limit)
            else:
                
                if radius_filter is not None:
                    geo_query_result = foodtrucks.find({ "loc" : { "$geoWithin" :{ "$centerSphere" :[ [ longitude, latitude ] , radius_filter / 3959 ]} } , "facilitytype":category_filter, "status":status} ).limit(limit)
                else:
                    geo_query_result = foodtrucks.find({ "loc" : { "$near" : [ longitude, latitude ] , $maxDistance: max_distance/69}, "facilitytype":category_filter, "status":status } ).limit(limit)
            if name is None and fooditems is None:
                result = list(geo_query_result)
            else:
                if name is not None and fooditems is None:
                    result = [foodtruck for foodtruck in list(geo_query) if re.search(name, foodtruck["applicant"])]
                    if sort == 1:
                        result = sorted(result, key=lambda x: x["applicant"])
                elif name is None and fooditems is not None:
                    result = [foodtruck for foodtruck in list(geo_query) if re.search(fooditems, foodtruck["fooditems"])]
                    if sort == 1:
                        result = sorted(result, key=lambda x: x["fooditems"])
                else:
                    result = [foodtruck for foodtruck in list(geo_query) if re.search(fooditems, foodtruck["fooditems"]) and re.search(name, foodtruck["applicant"])]
                    if sort == 1:
                        result = sorted(result, key=lambda x: x["applicant"])

        if bounds is not None:
            
	    

def getfoodtruckinfo():
    pass

def errorcodes():
    pass

def generalapilists():
    pass

def defaultoptions():
    pass

def cacheops():
    pass

def syncdatabase():
    pass

if __name__ == "__main__":
    pass
