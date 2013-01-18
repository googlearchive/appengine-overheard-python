#!/usr/bin/env python
#
# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Overheard: A social quote recording site.

Overheard allows users to add quotes and vote on them, with 
the most popular rising to the top of the rankings.

Demonstrates:
   * Paging   - both using fetch() and by a unique index
   * Decay    - Having older quotes fall from view over time without background processes
   * Sharding - Using per user count shards to create unique a unique index
   * Memcache

Decay:
  The underlying assumption in this design is that there are at 
  best a couple thousand votes per quote over the course of a day or two. 
  Votes will be created with the Quote they are about as their parent. 
  As new votes are added the rank and votesum for the parent Quote are updated.

  We don't have background tasks that can go back and adjust the current rankings 
  of quotes over time, so we need a way to rank quotes that puts fresher quotes 
  higher in the ranking in a scalable way that will work for a long period of time.

  The ranking algorithm will make use of integer properties being 64-bits. The 
  rank for each quote is calculated as:

     rank = created * DAY_SCALE + votesum

  created    = Number of days after 10/1/2008 that the quote created.
  DAY_SCALE  = This is a constant that determines how quickly votes 
               should decay (defaults to 4).
  votesum    = Sum of all +1 and -1 votes for a quote.

  Does this work? Presume the following scenario:

  Day 1 -  [quote 0 and 1 are added on Day 1 and
                get 5 and 3 votes respectively. Rank is q0, q1.]
                
   q0 (5) = 1 * 4 * 5 = 20
   q1 (3) = 1 * 4 * 3 = 12

  Day 2 -  [quote 0 and 1 get 3 and 0 more votes
              respectively. quote 2 is added and gets 3 votes. Rank is now q0, q2, q1]
              
   q0 (5) + (3) = 1 * 4 * 8 = 32
   q1 (3) + (0) = 1 * 4 * 3 = 12
   q2       (3) = 2 * 4 * 3 = 24

  Day 3 - [quote 2 gets one more vote. quote 3 is added and gets 5 votes.
             Rank is q3, q0, q2, q1]
             
   q0 (5) + (3)       = 1 * 4 * 8 = 32
   q1 (3) + (0)       = 1 * 4 * 3 = 12
   q2       (3) + (1) = 2 * 4 * 4 = 32
   q3             (5) = 3 * 4 * 5 = 60      

  Note that ties are possible, which means that rank for quotes will have 
  to be disambiguated since the application allows paging of ranked quotes.

   
"""

import cgi
import logging
import os
import urlparse
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
import models
import wsgiref.handlers

def get_greeting():
  """
  Generate HTML for the user to either logout or login,
  depending on their current state. Also returns progress_id and 
  progress_msg.
  
  progress_id - The number of the image to display
    that shows how many stars the user has earned
    for participating with the site. This is actually 
    a bit field with the first four bits being:
    
    Bit - Value - Description
    0   -   1   - Showing up
    1   -   2   - Logging in
    2   -   4   - Voting on at least one quote
    3   -   8   - Contributing at least one quote
  
  return: (greeting, progress_id, progress_msg)
  """
  user = users.get_current_user()
  progress_id = 1
  progress_msg = 'You get one star just for showing up.'
  if user:
    greeting = ('%s (<a class="loggedin" href="%s">sign out</a>)' % 
        (user.nickname(), cgi.escape(users.create_logout_url('/'))))
    progress_id = 3
    progress_msg = 'One more star for logging in.'
    has_voted, has_added_quote = models.get_progress(user)    
    if has_voted:
      progress_id |= 4
      progress_msg = ""
    if has_added_quote:
      progress_id |= 8
      progress_msg = ""      
  else:
    greeting = ("""<a  href=\"%s\">Sign in to vote or add 
        your own quote</a>.""" % cgi.escape(users.create_login_url("/")))
  return (progress_id, progress_msg, greeting)


def quote_for_template(quotes, user, page=0):
  """Convert a Quote object into a suitable dictionary for 
  a template. Does some processing on parameters and adds
  an index for paging.
  
  Args
    quotes:  A list of Quote objects.
  
  Returns
    A list of dictionaries, one per Quote object.
  """
  quotes_tpl = []
  index = 1 + page * models.PAGE_SIZE
  for quote in quotes:
    quotes_tpl.append({
      'id': quote.key().id(),
      'uri': quote.uri,
      'voted': models.voted(quote, user),
      'quote': quote.quote,
      'creator': quote.creator,
      'created': quote.creation_order[:10],
      'created_long': quote.creation_order[:19],
      'votesum': quote.votesum,
      'index':  index        
    })
    index += 1
  return quotes_tpl

def create_template_dict(user, quotes, section, nexturi=None, prevuri=None, page=0):
  """Bundle up all the values and generate a dictionary that can be used to 
  instantiate a base + base_quotelist template.

  Args
    user:     The logged in user object
    quotes:   List of Quote objects
    section:  The name of the section, either Popular or Recent.
    nexturi:  If paging, the URI of the next page, otherwise None.
    prevuri:  If paging, the URI of the previous page, otherwise None.
    page:     The number of the page we are displaying, used to offset the indices.

  Returns
    A dictionary 
  
  """
  progress_id, progress_msg, greeting = get_greeting()      
  template_values  = {
     'progress_id': progress_id,
     'progress_msg': progress_msg,
     'greeting': greeting,
     'loggedin': user,
     'quotes' : quote_for_template(quotes, user, page),
     'section': section,
     'nexturi': nexturi,
     'prevuri': prevuri
  }
  
  return template_values


class MainHandler(webapp.RequestHandler):
  """Handles the main page and adding new quotes."""

  def get(self):
    """The most popular quotes in order, broken into pages, 
       served as HTML."""
    user = users.get_current_user()
    page = int(self.request.get('p', '0'))
    quotes, next = models.get_quotes(page)
    if next:
      nexturi = '/?p=%d' % (page + 1)
    else:
      nexturi = None
    if page > 1:
      prevuri = '/?p=%d' % (page - 1)
    elif page == 1:
      prevuri = '/'
    else:
      prevuri = None

    template_values = create_template_dict(
        user, quotes, 'Popular', nexturi, prevuri, page
      )    
    template_file = os.path.join(os.path.dirname(__file__), 'templates/index.html')    
    self.response.out.write(template.render(template_file, template_values))
    
  def post(self):
    """Add a quote to the system."""
    user = users.get_current_user()
    text = self.request.get('newtidbit').strip()
    if len(text) > 500:
      text = text[:500]
    if not text:
      self.redirect('/')
      return
    uri = self.request.get('tidbituri').strip()
    parsed_uri = urlparse.urlparse(uri)

    progress_id, progress_msg, greeting = get_greeting()      

    if uri and ( not parsed_uri.scheme or not parsed_uri.netloc ):
      template_values  = {
         'progress_id': progress_id,
         'progress_msg': progress_msg,
         'greeting': greeting,
         'loggedin': user,
         'text' : text,
         'uri' : uri,
         'error_msg' : 'The supplied link is not a valid absolute URI'
      }
      template_file = os.path.join(os.path.dirname(__file__), 
          'templates/add_quote_error.html'
      )
      self.response.out.write(template.render(template_file, template_values))
    else:
      quote_id = models.add_quote(text, user, uri=uri)
      if quote_id is not None:
        models.set_vote(long(quote_id), user, 1)
        self.redirect('/recent/')
      else:
        template_values  = {
           'progress_id': progress_id,
           'progress_msg': progress_msg,
           'greeting': greeting,
           'loggedin': user,
           'text' : text,
           'uri' : uri,
           'error_msg' : 'An error occured while adding this quote, please try again.'
        }
        template_file = os.path.join(os.path.dirname(__file__), 
            'templates/add_quote_error.html'
          )    
        self.response.out.write(template.render(template_file, template_values))        


class VoteHandler (webapp.RequestHandler):
  """Handles AJAX vote requests."""

  def post(self):
    """Add or change a vote for a user."""
    user = users.get_current_user()
    if None == user:
      self.response.set_status(403, 'Forbidden')
      return
    quoteid = self.request.get('quoteid')
    vote = self.request.get('vote')
    if not vote in ['1', '-1']:
      self.response.set_status(400, 'Bad Request')
      return
    vote = int(vote)
    models.set_vote(long(quoteid), user, vote)


class RecentHandler(webapp.RequestHandler):
  """Handles the list of quotes ordered in reverse chronological order."""

  def get(self):
    """Retrieve an HTML page of the most recently added quotes."""
    user = users.get_current_user()
    offset = self.request.get('offset')
    page = int(self.request.get('p', '0'))
    logging.info('Latest offset = %s' % offset)
    if not offset:
      offset = None
    quotes, next = models.get_quotes_newest(offset)
    if next:
      nexturi = '?offset=%s&p=%d' % (next, page+1)
    else:
      nexturi = None

    template_values = create_template_dict(user, quotes, 'Recent', nexturi, prevuri=None, page=page)
    template_file = os.path.join(os.path.dirname(__file__), 'templates/recent.html')    
    self.response.out.write(template.render(template_file, template_values))


class FeedHandler(webapp.RequestHandler):
  """Handles the list of quotes ordered in reverse chronological order."""

  def get(self, section):
    """Retrieve a feed"""
    user = None
    if section == 'recent':    
      quotes, next = models.get_quotes_newest()
    elif section == 'popular':
      quotes, next = models.get_quotes()
    else:
      self.response.set_status(404, 'Not Found')
      return      

    template_values = create_template_dict(user, quotes, section.capitalize())
    template_file = os.path.join(os.path.dirname(__file__), 'templates/atom_feed.xml')    
    self.response.headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
    self.response.out.write(template.render(template_file, template_values))


class QuoteHandler (webapp.RequestHandler):
  """Handles requests for a single quote, such as a vote, or a permalink page"""
  
  def post(self, quoteid):
    """Delete a quote."""
    user = users.get_current_user()
    models.del_quote(long(quoteid), user)
    self.redirect('/')

  def get(self, quoteid):
    """Get a page for just the quote identified."""
    quote = models.get_quote(long(quoteid))
    if quote == None:
      self.response.set_status(404, 'Not Found')
      return      
    user = users.get_current_user()
    quotes = [quote]

    template_values = create_template_dict(user, quotes, 'Quote', nexturi=None, prevuri=None, page=0)
    template_file = os.path.join(os.path.dirname(__file__), 'templates/singlequote.html')
    self.response.out.write(template.render(template_file, template_values))

application = webapp.WSGIApplication(
    [
        ('/', MainHandler),
        ('/vote/', VoteHandler),
        ('/recent/', RecentHandler),
        ('/quote/(.*)', QuoteHandler),
        ('/feed/(recent|popular)/', FeedHandler),
    ], debug=True)

def main():
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()
