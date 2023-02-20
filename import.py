from pathlib import Path
from tqdm.notebook import tqdm
from time import sleep
import datetime
import json
import re
import requests

# UPDATE THESE VARIABLES
API_BASE_URL = "https://example.com"
MASTODON_ACCESS_TOKEN = ""
DATA_DIR = "../data/"  # Unzipped twitter data export
MEDIA_DIR = "../data/tweets_media/"  # media folder of twitter data export
TWITTER_USERNAME = "YourTwitterUsername"

# Test Mastodon bearer token
url = f"{API_BASE_URL}/api/v1/apps/verify_credentials"
HEADERS = {"Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"}
r = requests.get(url, headers=HEADERS)

print(r)

def post_status(data):
    HEADERS = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}",
        "Idempotency-Key": data["created_at"],
    }
    url = f"{API_BASE_URL}/api/v1/statuses"
    r = requests.post(url, data=data, headers=HEADERS)
    return r.json()


def load_tweets():
    with open(DATA_DIR + "tweets.js", "r", encoding="utf8") as f:
        raw = f.read()
    raw = raw.replace("window.YTD.tweets.part0 = ", "")
    tweets = json.loads(raw)
    tweets = [tweet["tweet"] for tweet in tweets]
    tweets = sorted(tweets, key=lambda d: int(d["id"]))
    return tweets


def to_timestamp(created_at):
    timestamp = datetime.datetime.strptime(created_at, "%a %b %d %X %z %Y").isoformat(
        timespec="seconds"
    )
    return timestamp


def replace_urls(tweet):
    if "full_text" in tweet:
        text = tweet["full_text"]
    else:
        text = tweet["text"]
    if "entities" in tweet and "urls" in tweet["entities"]:
        for url in tweet["entities"]["urls"]:
            text = text.replace(url["url"], url["expanded_url"])
    return text


def replace_usernames(text):
    text = re.sub(r"(\B\@[A-Za-z0-9_]{1,15})(\:)?", r"\1@twitter.com\2", text)
    return text


def tweet_to_toot(tweet):
    toot = {
        "status": replace_usernames(replace_urls(tweet)),
        "visibility": "public",
        "created_at": to_timestamp(tweet["created_at"]),
        "language": tweet["lang"],
    }
    return toot


tweets = load_tweets()
ids_dict = {}
counter = 0

for tweet in tqdm(tweets):
    print("Tweet number " + str(counter))
    counter += 1
    print(tweet)
    if tweet["id"] in ids_dict:
        # was already posted, we can skip it
        pass
    elif tweet["full_text"].startswith("RT @"):
        # ignore retweets
        pass
    elif tweet["full_text"].startswith("@"):
        # ignore tweets that start with tagging someone
        pass
    else:
        try:
            toot = tweet_to_toot(tweet)
            if "media" in tweet["entities"]:
                # upload media to append to the post
                media_ids = []
                for media in tweet["extended_entities"]["media"]:
                    image_path = f"{MEDIA_DIR}{tweet['id']}-{media['media_url_https'].split('/')[-1]}"
                    if not Path(image_path).is_file():
                        continue
                    file = open(image_path, "rb")
                    data = file.read()
                    url = f"{API_BASE_URL}/api/v2/media"
                    files = {"file": (image_path, data, "application/octet-stream")}
                    r = requests.post(url, files=files, headers=HEADERS)
                    sleep(1)
                    json_data = r.json()
                    media_ids.append(json_data["id"])
                    toot["status"] = toot["status"].replace(media["url"], "")
                toot["media_ids[]"] = media_ids
            if (
                "in_reply_to_screen_name" in tweet
                and tweet["in_reply_to_screen_name"] == TWITTER_USERNAME
            ):
                # if Tweet is part of a thread, get ID if previous post
                try:
                    toot["in_reply_to_id"] = ids_dict.get(
                        tweet["in_reply_to_status_id"]
                    )
                except:
                    print("======= FAILED!! ======= Error: " + err)
                    pass
            sleep(1)
            posted = post_status(toot)
            print("POSTED!!")
            print(posted)
            ids_dict[tweet["id"]] = posted["id"]
        except Exception as err:
            print("======= FAILED!! ======= Error: " + err)
            pass

with open("ids_dict.txt", "w") as f:
    f.write(json.dumps(ids_dict))
