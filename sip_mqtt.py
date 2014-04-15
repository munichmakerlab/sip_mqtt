# $Id$
#
# SIP account and registration sample. In this sample, the program
# will block to wait until registration is complete
#
# Copyright (C) 2003-2008 Benny Prijono <benny@prijono.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
#
import sys
import pjsua as pj
import threading
import re
import paho.mqtt.client as paho
from threading import Timer
import logging
import json

import config

def on_connect(mosq, obj, rc):
	logging.info("Connect with RC " + str(rc))
	
def on_disconnect(client, userdata, rc):
	logging.warning("Disconnected (RC " + str(rc) + ")")
	if rc <> 0:
		try_reconnect(client)

def on_log(client, userdata, level, buf):
	logging.debug(buf)

# MQTT reconnect
def try_reconnect(client, time = 60):
	try:
		logging.info("Trying reconnect")
		client.reconnect()
	except:
		logging.warning("Reconnect failed. Trying again in " + str(time) + " seconds")
		Timer(time, try_reconnect, [client]).start()

def log_cb(level, str, len):
	logging.debug(str)

class MyAccountCallback(pj.AccountCallback):
	sem = None

	def __init__(self, account):
		pj.AccountCallback.__init__(self, account)

	def wait(self):
		self.sem = threading.Semaphore(0)
		self.sem.acquire()

	def on_reg_state(self):
		if self.sem:
			if self.account.info().reg_status >= 200:
				self.sem.release()

	def on_incoming_call(self, call):
		regex = re.compile("<sip:(\d*)@.*>")
		r = regex.findall(call.info().remote_uri);
		logging.info("Incomming call from " + r[0])
		
		call_details = { "type": "CALL",
				"status" : call.info().state_text,
				"uri" : call.info().remote_uri,
				"number": r[0],
				"last_code": call.info().last_code
		}
		mqttc.publish(config.topic, json.dumps(call_details), 0, False)
		
		call_cb = MyCallCallback(call)
		call.set_callback(call_cb)
		
# Callback to receive events from Call
class MyCallCallback(pj.CallCallback):

	def __init__(self, call=None):
		pj.CallCallback.__init__(self, call)

	# Notification when call state has changed
	def on_state(self):
		logging.info("Call with " + self.call.info().remote_uri + " is " + 
				self.call.info().state_text + "last code = " + \
				str(self.call.info().last_code) + " (" +
				self.call.info().last_reason + ")"
			)
		call_details = { "type": "CALL",
				"status" : self.call.info().state_text,
				"uri" : self.call.info().remote_uri,
				"last_code": self.call.info().last_code
		}
		mqttc.publish(config.topic, json.dumps(call_details), 0, False)
		

lib = pj.Lib()
logging.basicConfig(format='[%(levelname)s] %(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

# initialize MQTT
logging.info("Initializing MQTT")
mqttc = paho.Client("")
mqttc.username_pw_set(config.broker["user"], config.broker["password"])
mqttc.connect(config.broker["hostname"], config.broker["port"], 60)
mqttc.on_connect = on_connect
mqttc.on_disconnect = on_disconnect
mqttc.on_log = on_log

try:
	logging.info("Initializing SIP")
	lib.init(log_cfg = pj.LogConfig(level=0, callback=log_cb))
	lib.create_transport(pj.TransportType.UDP, pj.TransportConfig(5060))
	lib.start()

	acc = lib.create_account(pj.AccountConfig(config.sip["proxy"], config.sip["user"], config.sip["password"]))

	acc_cb = MyAccountCallback(acc)
	acc.set_callback(acc_cb)
	acc_cb.wait()

	logging.info("Registration complete, status=" + str(acc.info().reg_status) + "(" + acc.info().reg_reason + ")")

	# Loop forever
	logging.info("Entering loop")
	mqttc.loop_forever()

except pj.Error, e:
	logging.error("SIP Exception: " + str(e))

# Clean up afterwards
logging.info("Cleanup")
lib.destroy()
lib = None
mqttc.disconnect()
