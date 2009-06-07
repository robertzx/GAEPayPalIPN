#!/usr/bin/env python
"""
Google App Engine Paypal IPN

See webapp.py for documentation on RequestHandlers and the URL
mapping at the bottom of this module.  

"""

__author__ = 'Bill Ferrell'

import cgi
import csv
import datetime
import htmlentitydefs
import math
import os
import re
import sgmllib
import sys
import time
import urllib
import logging
import wsgiref.handlers
import base64
import hmac
import sha
import traceback

from google.appengine.api import datastore
from google.appengine.api import datastore_types
from google.appengine.api import datastore_errors
from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api import mail
from google.appengine.api import urlfetch

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext import search
from google.appengine.ext import bulkload
from google.appengine.ext import db

from django.utils import simplejson
from django.http import HttpResponse


## Set logging level.
logging.getLogger().setLevel(logging.INFO)


# Set to true to see stack traces and template debugging information
_DEBUG = True

class BaseRequestHandler(webapp.RequestHandler):
  """The common class for all requests"""

  def handle_exception(self, exception, debug_mode):
      exception_name = sys.exc_info()[0].__name__
      exception_details = str(sys.exc_info()[1])
      exception_traceback = ''.join(traceback.format_exception(*sys.exc_info()))
      logging.error(exception_traceback)
      exception_expiration = 600 # seconds 
      mail_admin = #TODO: Insert an admin email address # must be an admin
      sitename = #TODO: Insert the sitename
      throttle_name = 'exception-'+exception_name
      throttle = memcache.get(throttle_name)
      if throttle is None:
          memcache.add(throttle_name, 1, exception_expiration)
          subject = '[%s] exception [%s: %s]' % (sitename, exception_name,
                                                 exception_details)
          mail.send_mail_to_admins(sender=mail_admin,
                                   subject=subject,
                                   body=exception_traceback)

      values = {}
      template_name = 'error.html'
      if users.is_current_user_admin():
        values['traceback'] = exception_traceback
      #values['traceback'] = exception_traceback
      directory = os.path.dirname(os.environ['PATH_TRANSLATED'])
      path = os.path.join(directory, os.path.join('templates', template_name))
      self.response.out.write(template.render(path, values, debug=_DEBUG))

  def generate(self, template_name, template_values={}):
    """Generates the given template values into the given template.

    Args:
        template_name: the name of the template file (e.g., 'index.html')
        template_values: a dictionary of values to expand into the template
    """

    # Populate the values common to all templates
    values = {
      #'user': users.GetCurrentUser(),
      'debug': self.request.get('deb'),
      'current_header': template_name,
    }
    values.update(template_values)
    directory = os.path.dirname(os.environ['PATH_TRANSLATED'])
    path = os.path.join(directory, os.path.join('templates', template_name))
    self.response.out.write(template.render(path, values, debug=_DEBUG))


class HomePageHandler(BaseRequestHandler):
  """
  Generates the home page.

  """
  def get(self):
    logging.info('Visiting the home page')
    self.generate('home.html', {
      #'title': 'Home',
      })


class PaypalIPNHandler(BaseRequestHandler):
  """
  Classes for accepting PayPal's Instant Payment Notification messages.
  See: https://www.paypal.com/ipn

  "data" looks something like this:

  {
      'business': 'your-business@example.com',
      'charset': 'windows-1252',
      'cmd': '_notify-validate',
      'first_name': 'S',
      'last_name': 'Willison',
      'mc_currency': 'GBP',
      'mc_fee': '0.01',
      'mc_gross': '0.01',
      'notify_version': '2.4',
      'payer_business_name': 'Example Ltd',
      'payer_email': 'payer@example.com',
      'payer_id': '5YKXXXXXX6',
      'payer_status': 'verified',
      'payment_date': '11:45:00 Aug 13, 2008 PDT',
      'payment_fee': '',
      'payment_gross': '',
      'payment_status': 'Completed',
      'payment_type': 'instant',
      'receiver_email': 'your-email@example.com',
      'receiver_id': 'CXZXXXXXQ',
      'residence_country': 'GB',
      'txn_id': '79F58253T2487374D',
      'txn_type': 'send_money',
      'verify_sign': 'AOH.JxXLRThnyE4toeuh-.oeurch23.QyBY-O1N'
  }
  """
  verify_url = "https://www.paypal.com/cgi-bin/webscr"

  def get(self):
    logging.info('Calling the PaypalIPNHandler via get. Bad.')
    self.redirect("/home")

  def post(self):
    """ Post method to accept PayPalData data."""
    logging.info('Calling the PaypalIPNHandler via post. Good.')
    logging.info('print dir(self.request.POST.items()): %s' % dir(self.request.POST.items()))
    logging.info('print self.request.POST.items(): %s' % self.request.POST.items())

    data = dict(self.request.POST.items())
    logging.info('data == %s' % str(data))
    # We need to post that BACK to PayPal to confirm it
    if self.verify(data):
        r = self.process(data)
    else:
        r = self.process_invalid(data)

  def process(self, data):
    logging.info('Verfication successful. process(data)')
    #Here you may want to store the data sent in the IPN in the datastore.
    #Here you might do something like send an email with the data.

    self.redirect("/home")

  def process_invalid(self, data):
    FAIL_ALERT_EMAIL = """Invalid data fail.""" #TODO: Update info
    logging.info('Verfication failed. process_invalid(data)')
    #Optionally may elect to store the data in the datastore.
    
    message = mail.EmailMessage(sender="" , #TODO: Insert sender.
                                subject="FAIL - Paypal IPN verification")
    message.to = "" #TODO: Insert email
    message.body = self.FAIL_ALERT_EMAIL % data
    message.send()


  def do_post(self, url, args):
    return urlfetch.fetch(
      url = url,
        method = urlfetch.POST,
        payload = urllib.urlencode(args)
    ).content

  def verify(self, data):
    args = {
        'cmd': '_notify-validate',
    }
    for k, v in data.items():
        args[k] = v.encode('utf-8')
    return self.do_post(self.verify_url, args) == 'VERIFIED'


# Map URLs to our RequestHandler classes above
_PAYPAL_URLS = [
# after each URL map we list the html template that is displayed
   ('/', HomePageHandler), #home.html
   ('/paypalipn', PaypalIPNHandler), # PayPal IPN URL
   ('/.*$', HomePageHandler), #home.html
]


def main():
  application = webapp.WSGIApplication(_PAYPAL_URLS,
                                       debug=webpagehandlers._DEBUG)
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
