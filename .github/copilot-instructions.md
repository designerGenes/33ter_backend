# 33ter - AI-Powered Code Solution App

- VERY IMPORTANT:  Make sure to use FULL directory paths any time you use a terminal command.  Do not use a command like "mkdir app/dir".  If the project directory is "$HOME/dev/33ter" then you would in this case use: 
"mkdir -p $HOME/dev/33ter/app/dir"
OR
"cd $HOME/dev/33ter && mkdir -p app/dir"


### FROZEN code sections
A FROZEN code or app section is one which must NOT be edited without explicit command to be UNFROZEN.
FROZEN parts of the app are considered (while FROZEN) to be the desired final state of that part of the app.  For example, if we have:
A python app section (FROZEN)
   - uses SocketIO
An iOS app section
   - uses some other communication that is not SocketIO

and I say "Update the two sections of our app to communicate", you should interpret this to mean:
"Do NOT change the python app's communication method.  DO change the iOS app to use SocketIO based on the configuration currently present in the python app."

## The current frozen list:
(none)


### CAREFUL tag
Whenever a command contains the "@careful" tag, you must interpret this to mean: "Do NOT make any code changes whatsoever in response to this command.  Instead, build a detailed plan for how you would achieve the result specified by this command.  Print out this entire plan, step by step, including the names of specific files, types and functions your plan would involve changing.  Again, you must NOT make any actual code changes.  When your entire plan of changes is printed out, review it from top to bottom TWICE and identify any potential bugs these steps would introduce.  After each review, adjust your plan of changes if needed to eliminate any potential bugs you have identified that the previous version of your plan of changes might have caused.  Once you are done, ask 'May I proceed?'.  Only upon a response of 'Proceed' should you then implement the changes described in your pristine, self-reviewed list."


### Dividing our app into logical screens
when I refer to
[Name]        |        [File]

Status screen | status_view.py 
Screenshot screen | screenshot_view.py 
Debug screen | debug_view.py 