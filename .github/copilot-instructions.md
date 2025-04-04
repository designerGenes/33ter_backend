# Threethreeter - AI-Powered Code Solution App

- VERY IMPORTANT:  Make sure to use FULL directory paths any time you use a terminal command.  Do not use a command like "mkdir app/dir".  If the project directory is "$HOME/dev/Threethreeter" then you would in this case use: 
"mkdir -p $HOME/dev/Threethreeter/app/dir"
OR
"cd $HOME/dev/Threethreeter && mkdir -p app/dir"


## FROZEN code sections
A FROZEN code or app section is one which must NOT be edited without explicit command to be UNFROZEN.
FROZEN parts of the app are considered (while FROZEN) to be the desired final state of that part of the app.  For example, if we have:
A python app section (FROZEN)
   - uses SocketIO
An iOS app section
   - uses some other communication that is not SocketIO

and I say "Update the two sections of our app to communicate", you should interpret this to mean:
"Do NOT change the python app's communication method.  DO change the iOS app to use SocketIO based on the configuration currently present in the python app."


## The @FixList command
Whenever you get a command that is just "@FixList", you must interpret this to mean "scan the 'tofixlist.md' file inside the closest '.github' directory.  This file contains small bugs and desired improvements I have found but not gotten around to fixing yet.  Take the first line item from the list which is not prefaced with '  __DONE__ '  and treat it as a prompt.  When you have completed addressing that prompt, add '  __DONE__  ' to the start of that list item in the relevant 'tofixlist.md' file. 

## CAREFUL tag
Whenever a command contains the "@careful" tag, you must interpret this to mean: "Do NOT make any code changes whatsoever in response to this command.  Instead, build a detailed plan for how you would achieve the result specified by this command.  Print out this entire plan, step by step, including the names of specific files, types and functions your plan would involve changing.  Again, you must NOT make any actual code changes.  When your entire plan of changes is printed out, review it from top to bottom TWICE and identify any potential bugs these steps would introduce.  After each review, adjust your plan of changes if needed to eliminate any potential bugs you have identified that the previous version of your plan of changes might have caused.  Once you are done, ask 'May I proceed?'.  Only upon a response of 'Proceed' should you then implement the changes described in your pristine, self-reviewed list."

## the @GOODMORNING command
Whenever you get a command that is just "@GOODMORNING", you must interpret this to mean "a new day has begun, so momentarily leave behind your memory of the project and recreate inside the nearest '.github' folder a document named 'implementationplan.md'.  If this file already exists, you may consume its contents for inspiration.  You need to analyze our ENTIRE currently focused project (which can be "Threethreeter" or its sub-projects "local python backend", "iOS receiver", or "Azure function" depending on our currently workspace contents).  You must then fill the nearest .github/implementationplan.md with four (4) elements:
1. a thorough explanation of the goal and functionality of this currently open workspace (which can again be either the entire project or one of the individual sub-projects)
2. a thorough, organized, step-by-step walkthrough of all conceptual behaviors which take place inside this project or all its sub-projects, in order to achieve the goal or functionality described above
3. a thorough, organized list of all remaining UNFINISHED or MISCONFIGURED or AMBIGUOUS elements of this project or all its sub-projects
4. a thorough, organized list of all (if any) functions or properties inside this project or all its sub-projects which are INACCESSIBLE, or never accessed (and thus should likely be removed)

### Dividing our app into logical screens
when I refer to
[Name]        |        [File]

Status screen | status_view.py 
Screenshot screen | screenshot_view.py 
Debug screen | debug_view.py