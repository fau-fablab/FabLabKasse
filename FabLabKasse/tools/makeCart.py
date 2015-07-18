#!/usr/bin/env python

import json
from sys import argv
import time

id = int(argv[1])

data = {}
data["cartCode"] = id
data["items"] = []

product = {}
product["id"] = 44
product["productId"] = "9011"
product["amount"] = "5.0"

data["items"].append(product)
data["status"] = "PENDING"
data["pushId"] = "000"
data["sendToServer"] = int(time.time())

f = open(str(id), "w")
f.write(json.dumps(data))
f.close()
