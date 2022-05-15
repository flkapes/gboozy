import json
import logging
import os.path
from datetime import datetime as dt

from singleton_decorator import singleton


@singleton
class Log:

	def __init__(self):

		file = open("config.json", "r")
		file = json.load(file)
		file = file['logging']
		filePath = os.path.join(os.path.abspath(".."), "logs")
		if not os.path.exists(filePath):
			os.mkdir(filePath)
		self.logger = logging.getLogger(file['loggerType'])
		self.logger.setLevel(logging.INFO)
		handler = logging.FileHandler(
			filename='logs/discord {}.log'.format(dt.now().strftime(file['dateTimeFormat'])),
			encoding=file['encoding'],
			mode='w')

		handler.setFormatter(logging.Formatter(
			file['handlerFormat']))
		self.logger.addHandler(handler)

	def info(self, message):
		self.logger.info(message)

	def warning(self, message):
		self.logger.warning(message)
