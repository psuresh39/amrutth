import json
from pymongo import MongoClient
from geopy.geocoders import GoogleV3

def authhandler():
    pass

def searchfoodtruck(location=None, bounds=None, point=None , limit=20, offset=0, sort=0, category_filter="", radius_filter=25, name="", status="", fooditems=""):
    if location == None and bounds == None and point == None:
        print("Some kind of location is needed")
        return
    elif ((location and bounds) or (location and point) or (point and location) or (location and bounds and point)):
        print("Use only one of the location methods")
        return
    else:
        #Make mongoDB query
        client = MongoClient()
        db = client.test
        foodtrucks = db.foodtrucks
        if location not None:
            address, (latitude, longitude) = geolocator.geocode(location)

        
	    

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

if __name__ == "__main__":


	
