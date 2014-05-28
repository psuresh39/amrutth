amrutth
=======

FOOD TRUCKS
------------
A service that tells the user what types of food trucks might be found near a specific location on a map.

Project is hosted on linode. Please visit www.amrutth.goz.cm/overview for API documentation.

Project is hosted on github: https://github.com/coolnay309/amrutth

- foodtruckapi.py - contains all the handlers
- foodtruckexceptions.py - contains custom exceptions used by this project
- tests/ - contains all the unittests
- html/ - contains all the api doc html files
- requirements - specifies all the requirements for this project

Special mentions:
------------------

- geopy (0.99) - for location to coordinate and distance calculations
- python-geoip (1.2) - to calculate location from ip address

Linode specifics: ssh moved to a different port, PermitRootLogin set to no, fail2ban to prevent dictionary attacks, setup firewall rules, auto reboot on kernel panic.

The technical track (1.5 years experience): backend (Tornado-python, Redis, mongoDB)

Design:
-------

MongoDB:
--------
Used mongoDB as the backend database. Mainly beacuse mongo has convinient geospatial queries and indexing. It has  a rich search via the text indexing. Below is the description of the indixes used and the size of indices. Since there were less inserts/updates, it made sense to use them without affecting performance. For 'loc' field 2d geospatial index was used. 2dshpere was not used because I assume here that the distance between points are not too large. Two separate indices were chosen because mongo does not allow creating a compund index of text and geospatial index.


    > db.foodtrucks.getIndexes()
    [
    	{
    		"v" : 1,
    		"key" : {
    			"_id" : 1
    		},
    		"name" : "_id_",
    		"ns" : "test.foodtrucks"
    	},
    	{
    		"v" : 1,
    		"key" : {
    			"loc" : "2d",
    			"facilitytype" : 1,
    			"status" : 1
    		},
    		"name" : "loc_2d_facilitytype_1_status_1",
    		"ns" : "test.foodtrucks"
    	},
    	{
    		"v" : 1,
    		"key" : {
    			"_fts" : "text",
    			"_ftsx" : 1
    		},
    		"name" : "applicant_text",
    		"ns" : "test.foodtrucks",
    		"weights" : {
    			"applicant" : 1
    		},
    		"default_language" : "english",
    		"language_override" : "language",
    		"textIndexVersion" : 2
    	}
    ]

    > db.foodtrucks.totalIndexSize()
    147168

Redis:
-------
Used redis as the cache on top of mongoDB. Redis stores the query dict as key and json response as value. Redis was setup to be an lru cache with 100mb cache size. This was decided after considering the current amount of RAM available. Also since mongoDB is running on the same machine which may cause swapping, I decided to limit redis size and evict least recently used records.

Tornado:
---------
Defines 3 handlers to handle static api docs, geo search and name search.
    
    
Trade-offs you might have made, anything you left out, or what you might do differently if you were to spend additional time on the project

Things that can be done in future:
----------------------------------

- Sync DB:
The DataSF database might be updated at which point the mongoDB that's hosted as part of this project would become stale. We need to be able to sync databases live. For the current we can just create a new collection and have the app point to the new collection. And toggle this point on. For more data it requires dealing with the diff, the diff can just be a oplog of transactions and we can apply thos to the collection. The collection would be locked for the time period. Data might come out stale for reads till the collection is being updated. Indexes would need to be rebuilt.

- Oauth:
Would be a nice to support 3rd party auth. Tornado has a tornado.auth that supports this. This would introduce people object which opens up many other features like reviewes, chat (eg vendor can post some deals since the foodtruck business is kind of in the moment and needs timely updates).

- Nagios, fabric:
Monitor website via nagios plugin.
Use fabric for deploying (do a git pull, restart service), starting, killing, collect and cleanup logs.

- FrontEnd:
This porject is missing frontend.