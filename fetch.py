#!/usr/bin/env python3

import json
import hashlib
import html
import os
import re
import urllib

import bs4

THIS_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)))

DEBUG = True
DEBUG_CACHE_DIR = os.path.join(THIS_DIR, 'debug-cache')

MAX_NO_NEW_REVIEWS = 3

TARGET_BASE_URL = 'https://www.yelp.com/biz/pike-s-surf-and-sk8-school-santa-barbara'
OUT_PATH = os.path.join(THIS_DIR, 'reviews.json')

# Replacements that Python tools are not catching.
REPLACEMENTS = [
    ["\n", ' '],
    ['<br>', ' '],
    ['&#39;', "'"],
    ["\u00a0", ' '],
]

HEADER = ['Date', 'User', 'Rating', 'Text']

def fetchPage(url):
    debugPath = os.path.join(DEBUG_CACHE_DIR, md5String(url))
    os.makedirs(DEBUG_CACHE_DIR, exist_ok = True)

    if (DEBUG and os.path.isfile(debugPath)):
        with open(debugPath, 'r') as file:
            return file.read()

    contents = str(urllib.request.urlopen(url).read().decode('utf-8'))

    if (DEBUG):
        with open(debugPath, 'w') as file:
            file.write(contents + "\n")

    return contents

def md5String(string):
    return str(hashlib.md5(string.encode()).hexdigest())

def createReviewHash(standardReview):
    contents = "\t".join([
        standardReview['author'],
        str(standardReview['rating']),
        standardReview['text'],
    ])

    return md5String(contents)

def cleanText(text):
    text = urllib.parse.unquote(html.unescape(text))

    for replacement in REPLACEMENTS:
        text = text.replace(replacement[0], replacement[1])

    return re.sub(r'\s+', ' ', text).strip()

# 'M/D/YYYY' -> 'YYYY-MM-DD'
def flipLocalDate(text):
    parts = text.split('/')
    return '-'.join([parts[2], ('0' + parts[0])[-2:], ('0' + parts[1])[-2:]])

def minePage(url):
    reviews = {}

    # The expected total number of reviews (not just the ones on this page).
    reviewCount = 0

    contents = fetchPage(url)
    document = bs4.BeautifulSoup(contents, features = 'lxml')

    for doc in document.select('script'):
        if (('type' not in doc.attrs) or (not doc['type'].endswith('json'))):
            continue

        contents = str(doc.contents[0])

        if (contents.startswith('<!--')):
            contents = contents.removeprefix('<!--').removesuffix('-->')

        try:
            data = json.loads(contents)
        except Exception as ex:
            '''
            print("Bad JSON")
            print(ex)
            print(contents)
            print('---')
            '''

        if (('@type' in data) and (data['@type'] == 'LocalBusiness')):
            reviewCount = max(reviewCount, data['aggregateRating']['reviewCount'])

            for review in data['review']:
                standardReview = {
                    'author': review['author'],
                    'rating': review['reviewRating']['ratingValue'],
                    'text': cleanText(review['description']),
                    'date': review['datePublished'],
                }

                id = createReviewHash(standardReview)
                reviews[id] = standardReview
        elif (('bizDetailsPageProps' in data) and ('reviewFeedQueryProps' in data['bizDetailsPageProps'])):
            reviewCount = max(reviewCount, data['bizDetailsPageProps']['reviewFeedQueryProps']['pagination']['totalResults'])

            for review in data['bizDetailsPageProps']['reviewFeedQueryProps']['reviews']:
                standardReview = {
                    'author': review['user']['markupDisplayName'],
                    'rating': review['rating'],
                    'text': cleanText(review['comment']['text']),
                    'date': flipLocalDate(review['localizedDate']),
                }

                id = createReviewHash(standardReview)
                reviews[id] = standardReview

    # print(json.dumps(reviews, indent = 4))

    return reviews, reviewCount

def main():
    allReviews = {}

    allReviews, reviewCount = minePage(TARGET_BASE_URL)

    # Keep a backup method of bailing out incase the counts Yelp gives are wrong.
    noNewReviewsCount = 0

    pageCount = 1
    while (len(allReviews) < reviewCount and noNewReviewsCount < MAX_NO_NEW_REVIEWS):
        url = TARGET_BASE_URL + "?start=%d" % (pageCount * 10)
        pageCount += 1

        newReviews, _= minePage(url)

        oldSize = len(allReviews)
        allReviews.update(newReviews)

        if (len(allReviews) == oldSize):
            noNewReviewsCount += 1

    with open(OUT_PATH, 'w') as file:
        json.dump(allReviews, file, indent = 4)

    # Output as tsv.
    print("\t".join(HEADER))
    for (id, review) in allReviews.items():
        print("\t".join([review['date'], review['author'], str(review['rating']), review['text']]))

if (__name__ == '__main__'):
    main()
