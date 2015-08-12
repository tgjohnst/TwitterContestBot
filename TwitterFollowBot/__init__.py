# -*- coding: utf-8 -*-

"""
This is a heavily modified version of TwitterFollowBot
Original version - Copyright 2015 Randal S. Olson

This file is part of the Twitter Bot library.

The Twitter Bot library is free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your option)
any later version.

The Twitter Bot library is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
the Twitter Bot library. If not, see http://www.gnu.org/licenses/.
"""
from __future__ import print_function
from twitter import Twitter, OAuth, TwitterHTTPError
import os
import sys
import time
import random
import json

class TwitterBot:

	"""
		Bot that automates several actions on Twitter, such as following users
		and favoriting tweets.
	"""

	def __init__(self, config_file="config.txt"):
		# this variable contains the configuration for the bot
		self.BOT_CONFIG = {}

		# this variable contains the authorized connection to the Twitter API
		self.TWITTER_CONNECTION = None

		self.bot_setup(config_file)

		# Used for random timers
		random.seed()

	def wait_on_action(self):
		min_time = 0
		max_time = 0
		if "FOLLOW_BACKOFF_MIN_SECONDS" in self.BOT_CONFIG:
			min_time = int(self.BOT_CONFIG["FOLLOW_BACKOFF_MIN_SECONDS"])

		if "FOLLOW_BACKOFF_MAX_SECONDS" in self.BOT_CONFIG:
			max_time = int(self.BOT_CONFIG["FOLLOW_BACKOFF_MAX_SECONDS"])

		if min_time > max_time:
			temp = min_time
			min_time = max_time
			max_time = temp

		wait_time = random.randint(min_time, max_time)

		if wait_time > 0:
			print("  Choosing time between %d and %d - waiting %d seconds before action" % (min_time, max_time, wait_time))
			time.sleep(wait_time)

		return wait_time
		
	def get_follows_list_from_disk(self):
		"""
			Returns the set of users that the user is currently following, from disk cache.
		"""
		follows_list = []
		with open(self.BOT_CONFIG["FOLLOWS_FILE"], "r") as in_file:
			for line in in_file:
				follows_list.append(int(line))
		return follows_list
	
	def get_seen_tweets_list_from_disk(self):
		"""
			Returns the set of users that the user is currently following, from disk cache.
		"""
		with open(self.BOT_CONFIG["SEEN_TWEETS_FILE"], "r") as in_file:
			seen_tweets_dict = json.load(in_file)
		return seen_tweets_dict

	def bot_setup(self, config_file="config.txt"):
		"""
			Reads in the bot configuration file and sets up the bot.

			Defaults to config.txt if no configuration file is specified.

			If you want to modify the bot configuration, edit your config.txt.
		"""

		with open(config_file, "r") as in_file:
			for line in in_file:
				line = line.split(":")
				parameter = line[0].strip()
				value = line[1].strip()

				if parameter in ["USERS_KEEP_FOLLOWING", "USERS_KEEP_UNMUTED", "USERS_KEEP_MUTED"]:
					if value != "":
						self.BOT_CONFIG[parameter] = set([int(x) for x in value.split(",")])
					else:
						self.BOT_CONFIG[parameter] = set()
				elif parameter in ["FOLLOW_BACKOFF_MIN_SECONDS", "FOLLOW_BACKOFF_MAX_SECONDS"]:
					self.BOT_CONFIG[parameter] = int(value)
				else:
					self.BOT_CONFIG[parameter] = value

		# make sure that the config file specifies all required parameters
		required_parameters = ["OAUTH_TOKEN", "OAUTH_SECRET", "CONSUMER_KEY",
							   "CONSUMER_SECRET", "TWITTER_HANDLE",
							   "ALREADY_FOLLOWED_FILE","FOLLOWS_FILE", "SEEN_TWEETS_FILE"]

		missing_parameters = []

		for required_parameter in required_parameters:
			if (required_parameter not in self.BOT_CONFIG or
					self.BOT_CONFIG[required_parameter] == ""):
				missing_parameters.append(required_parameter)

		if len(missing_parameters) > 0:
			self.BOT_CONFIG = {}
			raise Exception("Please edit %s to include the following parameters: %s.\n\n"
							"The bot cannot run unless these parameters are specified."
							% (config_file, ", ".join(missing_parameters)))

		# make sure all of the sync files exist locally
		for sync_file in [self.BOT_CONFIG["ALREADY_FOLLOWED_FILE"],
						  self.BOT_CONFIG["FOLLOWS_FILE"],
						  self.BOT_CONFIG["SEEN_TWEETS_FILE"]]:
			if not os.path.isfile(sync_file):
				with open(sync_file, "w") as out_file:
					out_file.write("")

		# check how old the follows sync files are and recommend updating them
		# if they are old
		if (time.time() - os.path.getmtime(self.BOT_CONFIG["FOLLOWS_FILE"]) > 86400):
			print("Warning: Your Twitter follower sync files are more than a day old. "
				  "It is highly recommended that you sync them by calling sync_follows() "
				  "before continuing.", file=sys.stderr)
				  
		# Read followers file from disk and store in the bot
		self.follows = self.get_follows_list_from_disk()
		self.seen_tweets = self.get_seen_tweets_list_from_disk()

		# create an authorized connection to the Twitter API
		self.TWITTER_CONNECTION = Twitter(auth=OAuth(self.BOT_CONFIG["OAUTH_TOKEN"],
													 self.BOT_CONFIG["OAUTH_SECRET"],
													 self.BOT_CONFIG["CONSUMER_KEY"],
													 self.BOT_CONFIG["CONSUMER_SECRET"]))

	def sync_remote_follows(self):
		"""
			Syncs the user's follows locally so it isn't necessary
			to repeatedly look them up via the Twitter API. This will also remove mistaken
			local follows, and add local follows marked remotely, while attempting to
			maintain the order of the local cache.

			Do not run this method too often, or it will quickly cause your
			bot to get rate limited by the Twitter API.
		"""
		print("Syncing remote follows with local cache...", file=sys.stdout)
		# sync the user's follows (accounts the user is following)
		following_status = self.TWITTER_CONNECTION.friends.ids(screen_name=self.BOT_CONFIG["TWITTER_HANDLE"])
		newFollows = set(following_status["ids"])
		next_cursor = following_status["next_cursor"]
		
		while next_cursor != 0:
			following_status = self.TWITTER_CONNECTION.friends.ids(screen_name=self.BOT_CONFIG["TWITTER_HANDLE"],
																   cursor=next_cursor)
			newFollows = newFollows | set(following_status["ids"])
			next_cursor = following_status["next_cursor"]
		removedFollows = [x for x in self.follows if x not in newFollows]
		self.follows = [x for x in self.follows if x in newFollows]
		print("Found %d local follows not in remote set and removed them" % (len(removedFollows)), file=sys.stdout)
		toAdd = [x for x in newFollows if x not in set(self.follows)]
		self.follows = self.follows + toAdd
		print("Found %d remote follows not in local cache and added them" % (len(toAdd)), file=sys.stdout)

	def sync_follows_to_disk(self):
		"""
			Syncs the user's follows to disk. 
		"""

		# sync the user's follows (accounts the user is following) to disk
		with open(self.BOT_CONFIG["FOLLOWS_FILE"], "w") as out_file:
			for follow in self.follows:
				out_file.write("%s\n" % (follow))
		with open(self.BOT_CONFIG["ALREADY_FOLLOWED_FILE"], "a") as out_file:
			for follow in self.follows:
				out_file.write("%s\n" % (follow))
				
	def sync_seen_tweets_to_disk(self):
		"""
			Syncs the user's seen tweets to disk. 
		"""
		# sync the user's seen tweet IDs to disk
		with open(self.BOT_CONFIG["SEEN_TWEETS_FILE"], "w") as out_file:
			json.dump(self.seen_tweets, out_file, indent=2)

	def get_do_not_follow_list(self):
		"""
			Returns the set of users the bot has already followed in the past.
		"""
		dnf_list = []
		with open(self.BOT_CONFIG["ALREADY_FOLLOWED_FILE"], "r") as in_file:
			for line in in_file:
				dnf_list.append(int(line))
		return set(dnf_list)
	
	def get_follows_list(self):
		"""
			Returns the set of users that the user is currently following.
		"""
		return self.follows
		
	def get_seen_tweets_list(self):
		"""
			Returns the dictionary of the most recently dealt with tweet for each search
		"""
		return self.seen_tweets
		
	def add_local_follower(self, id):
		"""
			Returns the dictionary of the most recently dealt with tweet for each search
		"""
		self.follows.append(id)
		
	def get_last_id(self, term):
		"""
			Returns just the last seen tweet ID for a given search
		"""
		return self.seen_tweets.get(term, 0)
		
	def set_last_id(self, term, id):
		"""
			Sets the last seen tweet for a given search term to the specified ID
		"""
		self.seen_tweets[term] = id

	def search_tweets(self, phrase, count=100, result_type="recent", since=0):
		"""
			Returns a list of tweets matching a phrase (hashtag, word, etc.).
		"""
		toRet = self.TWITTER_CONNECTION.search.tweets(q=phrase, result_type=result_type, count=count, since_id=since)
		return toRet["statuses"]
		
	def search_tweets_with_metadata(self, phrase, count=100, result_type="recent", since=0):
		"""
			Returns a list of tweets matching a phrase (hashtag, word, etc.).
		"""
		return self.TWITTER_CONNECTION.search.tweets(q=phrase, result_type=result_type, count=count, since_id=since)

	def unfollow_user(self,user_id):
		"""
			Unfollows a specific person, denoted by their user ID
		"""
		self.wait_on_action()
		self.TWITTER_CONNECTION.friendships.destroy(user_id=user_id)
		print("  Unfollowed %d" % (user_id))
		
	def unfollow_first_n_users(self,num_users):
		"""
			Unfollows a specific person, denoted by their user ID
		"""
		for i in range(num_users):
			self.unfollow_user(self.follows.pop(0)) # would be more efficient to use a queue...

	def auto_fav(self, searched_tweets):
		"""
			Favorites every tweet in a tweet search list
		"""

		for tweet in searched_tweets:
			try:
				# don't favorite your own tweets
				if tweet["user"]["screen_name"] == self.BOT_CONFIG["TWITTER_HANDLE"]:
					continue
				time.sleep(1) # Wait a second between favorites!
				searched_tweet = self.TWITTER_CONNECTION.favorites.create(_id=tweet["id"])
				print("  Favorited: %s" % (searched_tweet["text"].encode("utf-8")))

			# when you have already favorited a tweet, this error is thrown
			except TwitterHTTPError as api_error:
				# quit on rate limit errors
				if "rate limit" in str(api_error).lower():
					print("You have been rate limited. "
						  "Wait a while before running the bot again.", file=sys.stderr)
					return

				if "you have already favorited this status" not in str(api_error).lower():
					print("Error: %s" % (str(api_error)), file=sys.stderr)
					
	def auto_rt(self, searched_tweets):
		"""
			Retweets every tweet in a tweet search list
		"""

		for tweet in searched_tweets:
			try:
				# don't retweet your own tweets
				if tweet["user"]["screen_name"] == self.BOT_CONFIG["TWITTER_HANDLE"]:
					continue
				time.sleep(1) # Wait a second between retweets!
				searched_tweet = self.TWITTER_CONNECTION.statuses.retweet(id=tweet["id"])
				print("Retweeted: %s" % (searched_tweet["text"].encode("utf-8")))

			# when you have already retweeted a tweet, this error is thrown
			except TwitterHTTPError as api_error:
				# quit on rate limit errors
				if "rate limit" in str(api_error).lower():
					print("You have been rate limited. "
						  "Wait a while before running the bot again.", file=sys.stderr)
					return

				print("Error: %s" % (str(api_error)), file=sys.stderr)

	def auto_follow(self, searched_tweets):
		"""
			Follows everyone in a tweet search list
		"""
		following = self.get_follows_list()
		do_not_follow = self.get_do_not_follow_list()

		for tweet in searched_tweets:
			try:
				if (tweet["user"]["screen_name"] != self.BOT_CONFIG["TWITTER_HANDLE"] and
						tweet["user"]["id"] not in following and
						tweet["user"]["id"] not in do_not_follow):

					self.wait_on_action()

					self.TWITTER_CONNECTION.friendships.create(user_id=tweet["user"]["id"], follow=False)
					self.add_local_follower(tweet["user"]["id"])

					print("  Followed %s" %
						  (tweet["user"]["screen_name"]))

			except TwitterHTTPError as api_error:
				# quit on rate limit errors
				if "unable to follow more people at this time" in str(api_error).lower():
					print("You are unable to follow more people at this time. "
						  "Wait a while before running the bot again or gain "
						  "more followers.", file=sys.stderr)
					return

				# don't print "already requested to follow" errors - they're
				# frequent
				if "already requested to follow" not in str(api_error).lower():
					print("Error: %s" % (str(api_error)), file=sys.stderr)


	def auto_unfollow_all_following(self,count=None):
		"""
			Unfollows everyone that you are following(except those who you have specified not to)
		"""
		following = self.get_follows_list()

		for user_id in following:
			if user_id not in self.BOT_CONFIG["USERS_KEEP_FOLLOWING"]:

				self.wait_on_action()

				self.TWITTER_CONNECTION.friendships.destroy(user_id=user_id)
				print("Unfollowed %d" % (user_id))
				
	def filter_out_tweets_containing(self,searched_tweets,exclude_list):
		"""
			Filters out tweets containing certain phrases from a list
		"""
		origLen = len(searched_tweets)
		for phrase in exclude_list:
			searched_tweets = [tweet for tweet in searched_tweets if not (phrase in tweet["text"])]
			numRemoved = origLen - len(searched_tweets)
			if numRemoved > 0:
				print("  Removed %d tweets with the phrase %s in them" % (numRemoved, phrase))
				origLen = len(searched_tweets)
		return searched_tweets
		
	def filter_out_tweets_with_prefix(self,searched_tweets,prefix):
		"""
			Filters out tweets that start with a certain prefix
		"""
		origLen = len(searched_tweets)
		searched_tweets = [tweet for tweet in searched_tweets if not (tweet["text"].startswith(prefix))]
		numRemoved = origLen - len(searched_tweets)
		if numRemoved > 0:
			print("  Removed %d tweets that begun with %s" % (numRemoved, prefix))
		return searched_tweets
		
	def filter_only_tweets_containing(self,searched_tweets,include_list):
		"""
			Filters out tweets containing certain phrases from a 
		"""
		origLen = len(searched_tweets)
		for phrase in include_list:
			searched_tweets = [tweet for tweet in searched_tweets if (phrase in tweet["text"])]
			numRetained = len(searched_tweets)
			if numRetained > 0:
				print("Retained %d out of %d tweets with the phrase %s in them" % (numRetained,origLen,phrase))
				origLen = len(searched_tweets)
		return searched_tweets

	def send_tweet(self, message):
		"""
			Posts a tweet.
		"""
		return self.TWITTER_CONNECTION.statuses.update(status=message)
