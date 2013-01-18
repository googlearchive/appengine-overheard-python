/* 
Copyright 2008 Google Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

TODO Do something if the user clicks and isn't logged in.

*/
(function() {
   $(document).ready(
     function(){

      /* Only display and then fadeout the hint on the first page view. */
      if (document.referrer.match('http://just-overheard-it.appspot.com/') == null) {
        $('.gamehint').show().fadeOut(4000);
      }


      /* Dynamically handle giving a star the first time they vote. */
      function star_for_voting() {
          if ($('.login img').attr('src') == '/images/progress3.png') {
              $('.login img').attr('src', '/images/progress7.png');
              $('.gamehint').html('One more star for voting')
                  .show().fadeOut(4000);
          }
      }

      /* Callback functions attached to the onclick handlers
         for the up and down arrows for voting. They handle
         doing the ajax call to change the vote on the server
         and then upon success change the arrow colors to 
         match the vote. 
       */
      function votedown(e) {
        var parpar = $(e.target).parent().parent();
        var quoteid = parpar.find('.quoteid').html();
        var other = parpar.find('.votedown');
        $.post(
          '/vote/',
          {'quoteid': quoteid, 'vote': 1},
          function() {
              $(e.target).attr('src', '/images/up.png');
              $(other).attr('src', '/images/down-grey.png');
              star_for_voting();
          }
        );

        return false;
      }

      function voteup(e) {
        var parpar = $(e.target).parent().parent();
        var quoteid = parpar.find('.quoteid').html();
        var other = parpar.find('.voteup');
        $.post(
          '/vote/',
          {'quoteid': quoteid, 'vote': -1},
          function() {
              $(e.target).attr('src', '/images/down.png');
              $(other).attr('src', '/images/up-grey.png');
              star_for_voting();
          }
        );

        return false;
      }

      function should_login(e) {
          $('.loginwarning').show(300).fadeOut(4000);
      }

      
      if ($('.loggedin').length) {

         /* Attach the handlers to each up and down image to handle clicks for voting.  */
         $('.tidbits .voteup').each(
           function() {
               $(this).click(votedown);
           }
         );

         $('.tidbits .votedown').each(
           function() {
               $(this).click(voteup);
           }
         );
      } else {
         /* Attach the handlers to each up and down image to handle clicks.  */
         $('.tidbits .voteup').each(
           function() {
               $(this).click(should_login);
           }
         );

         $('.tidbits .votedown').each(
           function() {
               $(this).click(should_login);
           }
         );
      
      }
      

     }
   );
})();
