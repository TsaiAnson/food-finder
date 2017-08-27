import argparse
import json
import redis
import requests
import sys
import urllib

from urllib.error import HTTPError
from urllib.parse import quote
from urllib.parse import urlencode

# TODO
# Client_ID and Client_Secret constants (MUST REMOVE IF REPO IS PUBLIC)
CLIENT_ID = 'Atz_4eQ6jE5PY839AWdoAQ'
CLIENT_SECRET='raGawm10KZyS4pHsszfjKgE8LjjpIXkAehDfQeBVIIqwwHgKWCDOBQ2slAUMOdZI'

# Redis Client_ID
r = redis.StrictRedis(host='0.0.0.0', port=6379)

def getAuth():
    url = 'https://api.yelp.com/oauth2/token'
    data = urlencode({
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials',
    })
    headers = {
        'content-type': 'application/x-www-form-urlencoded',
    }
    response = requests.request('POST', url, data=data, headers=headers)
    auth_token = response.json()['access_token']
    return auth_token

def query_restaurants(session, location):
    # Check to see if there is already an auth_token with sessionID (with Redis)
    auth_token = r.hget(session, 'Auth_Token')
    if auth_token == None:
       auth_token = getAuth()
       r.hset(session, 'Auth_Token', auth_token)
    url_params = {
        'term': 'restaurants',
        'location': location.replace(' ', '+'),
        'radius' : 3200,
        'limit' : 20,
    }
    url = 'https://api.yelp.com/v3/businesses/search'
    headers = {
        'Authorization': 'Bearer {0}'.format(auth_token),
    }
    response = requests.request('GET', url, headers=headers, params=url_params).json()

    # Processing data for redis
    restaurants = {}
    categories = {}
    response = response['businesses']
    for restaurant_details in response:
        restaurant_details_trunc = {}
        category_map = {category_dict['title']:category_dict['alias'] for category_dict in restaurant_details['categories']}
        restaurant_details_trunc = {'category_map': category_map, "image_url": restaurant_details['image_url']}
        restaurants[restaurant_details['name']] = restaurant_details_trunc
        for alias in category_map.values():
            if alias not in categories:
                categories[alias] = 0
    r.hset(session, 'restaurants', json.dumps(restaurants))
    r.hset(session, 'categories', json.dumps(categories))

def next_restaurant(session, result=False, first=False):
    next = 'next'
    restaurants = json.loads(r.hget(session, 'restaurants'))

    # Check result of previous restaurant
    if not first:
        prev = r.hget(session, 'curr').decode('UTF-8')
    if result:
        categories = json.loads(r.hget(session, 'categories'))
        for c in restaurants[prev]['category_map'].values():
            categories[c] += 1
        r.hset(session, 'categories', json.dumps(categories))
        r.hset(session, 'restaurants', json.dumps(restaurants))
        if len(restaurants) == 1:
            next = 'results'
    if not first:
        restaurants.pop(prev)
    r.hset(session, 'restaurants', json.dumps(restaurants))
    if len(restaurants) == 0:
        return
    elif len(restaurants) == 1:
        next = 'results'

    # Assign new restaurant
    curr = list(restaurants.keys())[0]
    r.hset(session, 'curr', curr)
    msg = {"name": curr, 'categories': list(restaurants[curr]['category_map'].keys()), 'img': restaurants[curr]['image_url'], 'next': next}
    return json.dumps(msg)

# TODO: actually implement this
def get_recommend(session):
    categories = json.loads(r.hget(session, 'categories'))
    top = sorted(categories, key=categories.get, reverse=True)[:5]
    msg = {"name": "RESULTS", 'categories': top, 'img': 'http://thecatapi.com/api/images/get?format=src&type=gif', 'next': "None"}
    return json.dumps(msg)

# Used for unit testing
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--loc', type=str, help='Current Location')
    args = parser.parse_args()

    if not args.loc:
        print('Need to input Current Location')
        exit()

    try:
        if args.loc:
            query_restaurants(123456, args.loc)
    except HTTPError as error:
        sys.exit(
            'Encountered HTTP error {0} on {1}:\n {2}\nAbort program.'.format(
                error.code,
                error.url,
                error.read(),
            )
        )