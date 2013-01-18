import models
import os
import sys
import unittest
import time
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.api import apiproxy_stub_map
from google.appengine.api import urlfetch_stub
from google.appengine.api import user_service_stub

        
class TestModel(unittest.TestCase):
    
  def test_add_quote(self):
    """
    Add and remove quotes from the system.
    """
    user = users.User('joe@example.com')
    quoteid = models.add_quote('This is a test.', user)
    time.sleep(1.1)
    quoteid2 = models.add_quote('This is a test2.', user)
    self.assertNotEqual(quoteid, None)
    self.assertNotEqual(quoteid, 0)
    
    # Get the added quotes by creation order
    quotes, next = models.get_quotes_newest()
    self.assertEqual(quotes[0].key().id(), quoteid2)
    self.assertEqual(models.get_quote(quoteid2).key().id(), quoteid2)

    self.assertEqual(len(quotes), 2)
    
    # Remove one quote
    models.del_quote(quoteid2, user)

    quotes, next = models.get_quotes_newest()
    self.assertEqual(quotes[0].key().id(), quoteid)
    self.assertEqual(len(quotes), 1)
    

    # Remove last remaining quote    
    models.del_quote(quoteid, user)
    quotes, next = models.get_quotes_newest()
    self.assertEqual(len(quotes), 0)

  def test_del_quote_perms(self):
    """
    Permissions of removing quotes.
    """
    user = users.User('joe@example.com')
    user2 = users.User('fred@example.com')
    quoteid = models.add_quote('This is a test.', user)

    # Get the added quotes by creation order
    quotes, next = models.get_quotes_newest()
    self.assertEqual(quotes[0].key().id(), quoteid)
    self.assertEqual(len(quotes), 1)
    
    # Remove one quote, should fail to remove the quote
    models.del_quote(quoteid, user2)

    # Confirm the quote is still in the system
    quotes, next = models.get_quotes_newest()
    self.assertEqual(quotes[0].key().id(), quoteid)
    self.assertEqual(len(quotes), 1)

    # Remove one remaining quote    
    models.del_quote(quoteid, user)
    quotes, next = models.get_quotes_newest()
    self.assertEqual(len(quotes), 0)

    
  def test_del_non_existent(self):
    user = users.User('joe@example.com')
    models.del_quote(1, user)
    
  def test_paging_newest(self):
    """
    Test that we can page through the quotes in 
    the order that they were added.
    """
    user = users.User('joe@example.com')
    for i in range(models.PAGE_SIZE):
      quoteid = models.add_quote('This is a test.', user)
      self.assertNotEqual(quoteid, None)
    quotes, next = models.get_quotes_newest()
    self.assertEqual(len(quotes), models.PAGE_SIZE)
    self.assertEqual(next, None)

    quoteid = models.add_quote('This is a test.', user)
    self.assertNotEqual(quoteid, None)
    
    quotes, next = models.get_quotes_newest()
    
    self.assertEqual(len(quotes), models.PAGE_SIZE)
    self.assertNotEqual(next, None)
    
    quotes, next = models.get_quotes_newest(next)
    self.assertEqual(len(quotes), 1)
    self.assertEqual(next, None)

    # Cleanup    
    models.del_quote(quoteid, user)
    quotes, next = models.get_quotes_newest()
    for q in quotes:
      models.del_quote(q.key().id(), user)
    
  def test_game_progress(self):
    email = 'fred@example.com'
    user = users.User(email)

    hasVoted, hasAddedQuote = models.get_progress(user)
    self.assertFalse(hasVoted)
    self.assertFalse(hasAddedQuote)

    quoteid0 = models.add_quote('This is a test.', user, _created=1)
    
    hasVoted, hasAddedQuote = models.get_progress(user)
    self.assertFalse(hasVoted)
    self.assertTrue(hasAddedQuote)
    
    models.set_vote(quoteid0, user, 1)
    
    hasVoted, hasAddedQuote = models.get_progress(user)
    self.assertTrue(hasVoted)
    self.assertTrue(hasAddedQuote)
    
  def test_voting(self):
    """
    Test the voting system behaves as defined in the 
    design document.
    """
    user = users.User('fred@example.com')
    user2 = users.User('barney@example.com')
    
    # Day 1 -  [quote 0 and 1 are added on Day 1 and
    #            get 5 and 3 votes respectively. Rank is q0, q1.]
    # q0 (5) = 1 * 4 + 5 = 9 
    # q1 (3) = 1 * 4 + 3 = 7 

    quoteid0 = models.add_quote('This is a test.', user, _created=1)
    quoteid1 = models.add_quote('This is a test.', user, _created=1)    
    models.set_vote(quoteid0, user, 1)
    models.set_vote(quoteid1, user, 3)
    quotes, next = models.get_quotes()

    self.assertEqual(models.voted(quotes[1], user), 1)
    self.assertEqual(models.voted(quotes[0], user), 3)

    self.assertEqual(quotes[0].key().id(), quoteid1)
    self.assertEqual(quotes[1].key().id(), quoteid0)
    
    models.set_vote(quoteid0, user, 5)
    quotes, next = models.get_quotes()
    self.assertEqual(quotes[0].key().id(), quoteid0)
    self.assertEqual(quotes[1].key().id(), quoteid1)

    # q0 (5) + (3) = 1 * 4 + 8 = 12
    # q1 (3) + (0) = 1 * 4 + 3 = 7 
    # q2       (3) = 2 * 4 + 3 = 11
    quoteid2 = models.add_quote('This is a test.', user, _created=2)

    models.set_vote(quoteid0, user, 8)
    models.set_vote(quoteid1, user, 3)
    models.set_vote(quoteid2, user, 3)
    quotes, next = models.get_quotes()

    self.assertEqual(quotes[0].key().id(), quoteid0)
    self.assertEqual(quotes[1].key().id(), quoteid2)
    self.assertEqual(quotes[2].key().id(), quoteid1)


    # q0 (5) + (3)       = 1 * 4 + 8 = 12 
    # q1 (3) + (0)       = 1 * 4 + 3 = 7
    # q2       (3) + (2) = 2 * 5 + 4 = 14
    # q3             (5) = 3 * 4 + 5 = 17      

    quoteid3 = models.add_quote('This is a test.', user, _created=3)

    models.set_vote(quoteid0, user, 8)
    models.set_vote(quoteid1, user, 3)
    models.set_vote(quoteid2, user, 5)
    models.set_vote(quoteid3, user, 5)
    quotes, next = models.get_quotes()
    
    self.assertEqual(quotes[0].key().id(), quoteid3)
    self.assertEqual(quotes[1].key().id(), quoteid2)
    self.assertEqual(quotes[2].key().id(), quoteid0)
    self.assertEqual(quotes[3].key().id(), quoteid1)


    # q0 (5) + (3) + (1) = 1 * 4 + 9 = 13
    # q1 (3) + (0)       = 1 * 4 + 3 = 7 
    # q2       (3) + (2) = 2 * 5 + 4 = 14
    # q3             (0) = 3 * 4 + 0 = 12      

    models.set_vote(quoteid0, user, 9)
    models.set_vote(quoteid3, user, 0)
    quotes, next = models.get_quotes()

    self.assertEqual(quotes[0].key().id(), quoteid2)
    self.assertEqual(quotes[1].key().id(), quoteid0)
    self.assertEqual(quotes[2].key().id(), quoteid3)
    self.assertEqual(quotes[3].key().id(), quoteid1)

    models.del_quote(quoteid0, user)
    models.del_quote(quoteid1, user)
    models.del_quote(quoteid2, user)
    models.del_quote(quoteid3, user)

    
if __name__ == '__main__':
    unittest.main()

    
