# -*- coding: utf8 -*-
#Dependancies: pymysql, fastapi, uvicorn, sqlalchemy, (mysql-connector?), mysql-server (apt), pydantic (internal)
from fastapi import FastAPI, Form, File
from pydantic import BaseModel
from fastapi import Query
import asyncio
import sqlalchemy.ext.declarative
import sqlalchemy.orm
import sqlalchemy.orm.session
import sqlalchemy
import datetime
import threading
import os
import time
import random
import copy
import pickle

MYSQL_URL = "mysql+mysqlconnector://myuser:mypassword@127.0.0.1:3306/redacted"
BASE= sqlalchemy.ext.declarative.declarative_base()

#if error is caught timeout should be initated by an async function
sql_timeout = False

class Map(BASE):
	__tablename__ = "uploadData"
	uid = sqlalchemy.Column(sqlalchemy.BIGINT, primary_key=True)
	author =sqlalchemy.Column(sqlalchemy.String)
	json_file = sqlalchemy.Column(sqlalchemy.String)
	map_name=sqlalchemy.Column(sqlalchemy.String)
	completed_count=sqlalchemy.Column(sqlalchemy.Integer, default=0)
	views=sqlalchemy.Column(sqlalchemy.BIGINT, default=0)
	rank_score=sqlalchemy.Column(sqlalchemy.FLOAT, default=0)

engine = sqlalchemy.create_engine(MYSQL_URL, encoding="utf8", echo=False, pool_size=20, max_overflow=-1, )
sqlalchemy.orm.session.Session = sqlalchemy.orm.sessionmaker(bind=engine)



app = FastAPI()

upload_queue = []
uploading = False


def log_action(action_name):
	f = open("ac.log", "a")
	f.write(action_name + " " + time.asctime() + "\n")
	f.close()

def wait_timeout():
	global sql_timeout
	sql_timeout = True
	time.sleep(120)
	sql_timeout = False

@app.get("/queue_data") #debug for upload
async def get_queue_data():
	global upload_queue
	return "length of upload queue is " + str(len(upload_queue)) + " and uploading is " + str(uploading)

@app.post("/items_new") #new method of transferring data
async def create_item_newer(author:str = Form(...), map_name:str = Form(...), bodyData: str = Form(...)): #mutliple uploads to finish; 0=not finished, 1=finished, session id is a random integer generated by user to prevent corrupted upload files
	log_action("items_new")
	session = sqlalchemy.orm.session.Session()
	js = bodyData
	new_name = map_name.replace("\'", "")
	new_name = new_name.replace("\"", "")
	new_name = new_name.replace("\\", "")
	new_author = author.replace("\'", "")
	new_author = new_author.replace("\"", "")
	new_author = new_author.replace("\\", "")
	if (session.query(Map).filter_by(author=new_author, map_name=new_name).count() > 0):
		print("duplicate")
		return "duplicate author and name"

	actual_map = Map(author=new_author, json_file=js, map_name=new_name)
	global uploading
	global upload_queue
	if uploading:
		upload_queue.append(actual_map)
	else:
		threading.Thread(target=wait_upload_map, args=(actual_map,)).start()

	session.close()
	return "post successful"


def wait_upload_map(actual_map):
	log_action("wait_upload_map")
	global uploading
	global sql_timeout
	try:
		global upload_queue
		uploading = True
		session = sqlalchemy.orm.session.Session()
		session.add(actual_map)
		session.commit()

		#go through maps waiting to be uploaded
		my_queue = []
		while len(upload_queue) > 0: #if new things are added to the dictionary in the small loop it is repeatedly iterated
			#if timed out wait until changed
			while sql_timeout:
				print("timing out upload")
				time.sleep(10)

			my_queue += upload_queue
			upload_queue = []
			for m in my_queue:
				session.add(m)
			my_queue = []
			session.commit()
		session.close()
	except:
		if not sql_timeout:
			print("error with map uploading; timeout starts")
			threading.Thread(target=wait_timeout).start()
	uploading = False

#debug
@app.get("/uploading")
async def is_uploading():
	global uploading
	return uploading

@app.get("/author")
async def author_items(author:str, item_index: int, count: int):
	log_action("author_find")
	session = sqlalchemy.orm.session.Session()
	row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).filter(Map.author.op("regexp")(f".*{author}.*")).filter(Map.rank_score != -1).order_by(Map.uid.desc()).offset(item_index).limit(count)
	my_list = []
	for (index, i) in enumerate(row):
		my_list.append([i.map_name, i.author, i.views, i.completed_count, i.uid])
	session.close()
			
	return create_json(my_list)

@app.get("/map_name")
async def map_name_search(map_name: str, item_index:int, count:int):
	log_action("map_find")
	session = sqlalchemy.orm.session.Session()
	#row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).filter_by(map_name=map_name).order_by(Map.uid.desc()).offset(item_index).limit(count)
	row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).filter(Map.map_name.op("regexp")(f".*{map_name}.*")).filter(Map.rank_score != -1).order_by(Map.uid.desc()).offset(item_index).limit(count)
	my_list = []
	for (index, i) in enumerate(row):
		my_list.append([i.map_name, i.author, i.views, i.completed_count, i.uid])
	
	session.close()

	return create_json(my_list)

#this version ignores whether the map is censored or not (marked rank_score = -1) for moderators to ban/unban a map
@app.get("/author_uncensored")
async def author_items_uncensored(author:str, item_index: int, count: int):
	session = sqlalchemy.orm.session.Session()
	row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).filter(Map.author.op("regexp")(f".*{author}.*")).order_by(Map.uid.desc()).offset(item_index).limit(count)
	my_list = []
	for (index, i) in enumerate(row):
		my_list.append([i.map_name, i.author, i.views, i.completed_count, i.uid])
	session.close()
			
	return create_json(my_list)

@app.get("/map_name_uncensored")
async def map_name_uncensored(map_name: str, item_index:int, count:int):
	session = sqlalchemy.orm.session.Session()
	#row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).filter_by(map_name=map_name).order_by(Map.uid.desc()).offset(item_index).limit(count)
	row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).filter(Map.map_name.op("regexp")(f".*{map_name}.*")).order_by(Map.uid.desc()).offset(item_index).limit(count)
	my_list = []
	for (index, i) in enumerate(row):
		my_list.append([i.map_name, i.author, i.views, i.completed_count, i.uid])
	
	session.close()

	return create_json(my_list)

@app.get("/mark_map") #mark value sets the rank score (if -1 it will be banned and if not it can be shown)
async def mark_censor(author: str, map_name: str, password: str, mark_value: int):
	if (password != "ArmchairCommander_Admin"):
		return "incorrect password"
	
	threading.Thread(target=actually_mark_map, args=(author, map_name, mark_value)).start()
	return "updated censor settings"
def actually_mark_map(author: str, map_name: str, mark_value: int):
	session = sqlalchemy.orm.session.Session()
	row = session.query(Map).filter_by(author=author, map_name=map_name)
	if (len(row.all()) == 0):
		return "cannot find map"
	row.update({"rank_score": mark_value})
	session.commit()
	session.close()

@app.get("/most_recent")
async def newest_items(item_index: int, count: int):
	log_action("most_recent")
	count = min(count, 10)
	session = sqlalchemy.orm.session.Session()
	row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).order_by(Map.uid.desc()).offset(item_index).limit(count)
	my_list = []
	for (index, i) in enumerate(row):
		my_list.append([i.map_name, i.author, i.views, i.completed_count, i.uid])
	session.close()
	return create_json(my_list)

featured_names = []
featured_authors = []

@app.get("/add_one_featured")
async def add_one_featured(map_name: str, author: str, password: str):
	if password != "redacted":
		return "wrong password"
	for i in range(len(featured_names)):
		if featured_names[i] == map_name and featured_authors[i] == author:
			return "already featured!"

	session = sqlalchemy.orm.session.Session()
	row = session.query(Map.uid).filter_by(author=author, map_name=map_name)

	row_count = row.count()
	session.close()

	if row_count == 1:
		featured_names.append(map_name)
		featured_authors.append(author)
	else:
		return "failed"

	return "success"
@app.get("/add_featured") #to add multiple, [" \ "] will be used to split maps
async def add_featured(names_and_authors: str, password: str):
	if password != "redacted":
		return "wrong password"
	all_maps = names_and_authors.split(" \\ ")
	if len(all_maps) % 2 != 0:
		return "not an even number of inputs!"
	#returns the maps that could not be found in database
	cannot_find_maps = ""
	session = sqlalchemy.orm.session.Session()
	for i in range(int(len(all_maps) / 2)):
		row = session.query(Map.uid).filter_by(author=all_maps[i * 2 + 1], map_name=all_maps[i * 2])
		if row.count() == 1:
			featured_names.append(all_maps[i * 2])
			featured_authors.append(all_maps[i * 2 + 1])
		else:
			cannot_find_maps += all_maps[i * 2] + "/" + all_maps[i * 2 + 1]
	session.close()

	if cannot_find_maps == "":
		cannot_find_maps = "nothing"
	return "success; failed to add: " + cannot_find_maps
@app.get("/remove_featured")
async def remove_featured(name: str, author: str, password: str):
	if password != "redacted":
		return "wrong password"
	for i in range(len(featured_names)):
		if featured_names[i] == name and featured_authors[i] == author:
			featured_names.pop(i)
			featured_authors.pop(i)
			return "success"
	return "not found"
@app.get("/remove_all_featured")
async def remove_all_featured(password: str):
	if password != "redacted":
		return "wrong password"
	global featured_authors, featured_names
	featured_names = []
	featured_authors = []
	return "success"

@app.get("/get_all_featured")
async def get_all_featured():
	output_str = ""
	for i in range(len(featured_names)):
		output_str += featured_names[i] + " \\ "
		output_str += featured_authors[i] + " \\ "
	return output_str

@app.get("/featured")
async def featured_items(item_index: int, count: int):
	#prevent calling an absurdly large number and crashing server
	count = min(count, 10)
	session = sqlalchemy.orm.session.Session()
	my_list = []
	for i in range(len(featured_names) - item_index - count, len(featured_names) - item_index):
		if len(featured_names) > i and i >= 0:
			row = session.query(Map.views, Map.completed_count, Map.uid).filter_by(author=featured_authors[i], map_name=featured_names[i])
			if row.count() > 0:
				my_list.append([featured_names[i], featured_authors[i], row[0].views, row[0].completed_count, row[0].uid]) #won't show likes and views in featured
			else: #cannot find map
				my_list.append([featured_names[i], featured_authors[i], -1, -1, -1]) #won't show likes and views in featured

	session.close()
	my_list.reverse()
	return create_json(my_list)

@app.get("/popular")
async def popular_items(item_index: int, count: int):
	log_action("popular")
	count = min(count, 10)
	session = sqlalchemy.orm.session.Session()
	row = session.query(Map.views, Map.author, Map.completed_count, Map.map_name, Map.uid).order_by(Map.rank_score.desc(), Map.views.desc(), Map.completed_count.desc(), Map.uid.desc()).offset(item_index).limit(count)
	my_list = []
	for (index, i) in enumerate(row):
		my_list.append([i.map_name, i.author, i.views, i.completed_count, i.uid])
	session.close()
	
	return create_json(my_list)

@app.get("/server_time") #only on the official server to prevent using different time zone
async def return_time():
	log_action("server_time")
	return time.time()

@app.get("/items_get_new") #old has been removed for optimization
async def get_item_new(map_id: int, author: str, map_name: str, downloaded: int):
	#global adding_view
	#threading.Thread(target=wait_retrieve_map, args=(author, map_name, map_id, downloaded)).start()
	
	return wait_retrieve_map(author, map_name, map_id, downloaded)

	#return "session timeout"

adding_view = False
def wait_retrieve_map(author, map_name, map_id, downloaded):
	session = sqlalchemy.orm.session.Session()
	try:
		start_time = time.time()
		if (downloaded == 0):
			add_view_pool.append((author, map_name, map_id))
			global adding_view
			if not adding_view:
				threading.Thread(target=wait_add_metrics, args=(True,)).start()

		row = None
		if (map_id == -1):
			row = session.query(Map).filter_by(author=author, map_name=map_name)
		else:
			row = session.query(Map).filter_by(uid=map_id)

		if (row.count() == 0):
			print("cannot find map")
			session.close()
			return "map_error"
		
		print(f"retrieve time: {int(time.time() - start_time)}s")
		session.close()
		return row.one().json_file
	except:
		session.close()
		return "sql_error"
	

#waits to process the data, first element is map second element is author, third element is id 
#(tuple; only the third element actually matters if it exists (if ID is given, the time complexity goes to O(log(n)))
add_view_pool = [] 
add_like_pool = []

def wait_add_metrics(is_view:bool): #view or likes
	global sql_timeout
	session = sqlalchemy.orm.session.Session()
	if is_view:
		global adding_view
		global add_view_pool
		try:
			adding_view = True

			while len(add_view_pool) > 0: #if new things are added to the dictionary in the small loop it is repeatedly iterated
				my_pool = copy.deepcopy(add_view_pool)
				for d in my_pool: #do the process here
					print(f"{len(add_view_pool)} views remaining")
					actually_add_view(d[0], d[1], d[2], session)
					session.commit()
					add_view_pool.pop(0)
		except:
			if not sql_timeout:
				print(f"error with add view; timeout starts... queue length: {len(add_view_pool)}")
				threading.Thread(target=wait_timeout).start()
		adding_view = False
	else:
		global adding_like
		global add_like_pool
		try:
			adding_like = True

			while len(add_like_pool) > 0: #if new things are added to the dictionary in the small loop it is repeatedly iterated
				my_pool = copy.deepcopy(add_like_pool)
				for d in my_pool: #do the process here
					print(f"{len(add_like_pool)} likes remaining")
					actually_add_like(d[0], d[1], d[2], session)
					session.commit()
					add_like_pool.pop(0)		
		except:
			if not sql_timeout:
				print(f"error with add like; timeout starts... queue length: {len(add_like_pool)}")
				threading.Thread(target=wait_timeout).start()
		adding_like = False
	session.close()

def actually_add_view(author, map_name, map_id, session):
	log_action("add_view")
	#if timed out just call this again
	global sql_timeout
	if sql_timeout:
		return

	row = None
	if (map_id == -1):
		#discontinue in the future because it is very slow
		row = session.query(Map.views, Map.uid, Map.author, Map.completed_count, Map.map_name).filter_by(author=author, map_name=map_name)
	else:
		row = session.query(Map.views, Map.uid, Map.author, Map.completed_count, Map.map_name).filter_by(uid=map_id)
	if (row.count() == 0):
		return "cannot find map"
	v = row.one().views
	row.update({"views": int(v) + 1})
	
	
def actually_add_like(author, map_name, map_id, session):
	global sql_timeout
	if sql_timeout:
		return

	row = None
	if (map_id == -1):
		#discontinue this in the future
		row = session.query(Map.uid, Map.author, Map.completed_count, Map.map_name).filter_by(author=author, map_name=map_name)
	else:
		row = session.query(Map.uid, Map.author, Map.completed_count, Map.map_name).filter_by(uid=map_id)
	if (row.count() == 0):
		return "cannot find map"
	v = row.one().completed_count
	row.update({"completed_count": int(v) + 1})

adding_like = False
@app.get("/add_like_new")
async def add_like_new(author: str, map_name: str, map_id: int):
	log_action("add_like")
	add_like_pool.append((author, map_name, map_id))
	global adding_like
	if not adding_like:
		threading.Thread(target=wait_add_metrics, args=(False,)).start()

@app.get("/add_completed")
async def add_completed(author: str, map_name: str):
	log_action("add_like")
	add_like_pool.append((author, map_name, -1))
	global adding_like
	if not adding_like:
		threading.Thread(target=wait_add_metrics, args=(False,)).start()
		

def create_json(my_list):
	session = sqlalchemy.orm.session.Session()
	s = "{'strData':["
	for index, i in enumerate(my_list):
		s += "{'map_name':'" + i[0] + "',"
		s += "'author':'" + str(i[1]) + "',"
		s += "'views':" + str(i[2]) + ","
		s += "'completed_count':" + str(i[3]) + ","
		s += "'uid':" + str(i[4]) + "}"
		if (index < len(my_list) - 1):
			s += ","
	s += "]}"
	session.close()
	return s

import uvicorn
uvicorn.run(app, port=9999, host="0.0.0.0")



