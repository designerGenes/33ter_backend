# 33ter - AI-Powered Code Solution App

- VERY IMPORTANT:  Make sure to use FULL directory paths any time you use a terminal command.  Do not use a command like "mkdir app/dir".  If the project directory is "$HOME/dev/33ter" then you would in this case use: 
"mkdir -p $HOME/dev/33ter/app/dir"
OR
"cd $HOME/dev/33ter && mkdir -p app/dir"


## FROZEN code sections
A FROZEN code or app section is one which must NOT be edited without explicit command to be UNFROZEN.
FROZEN parts of the app are considered (while FROZEN) to be the desired final state of that part of the app.  For example, if we have:
A python app section (FROZEN)
   - uses SocketIO
An iOS app section
   - uses some other communication that is not SocketIO

and I say "Update the two sections of our app to communicate", you should interpret this to mean:
"Do NOT change the python app's communication method.  DO change the iOS app to use SocketIO based on the configuration currently present in the python app."

The current frozen list:
- the Azure functions and their related Firebase/Firestore code

## Application Overview
33ter is a mobile application that helps developers solve coding problems by capturing code snippets through OCR, processing them with AI, and presenting formatted solutions.

## Detailed Application Flow

### 1. iOS Client Flow (Mobile App)
1. User Authentication:
   - Handle user login/registration via Firebase
   - Validate subscription status
   - Cache authentication tokens

2. Main Application Flow:
   - User triggers screenshot of Macbook screen, ostensibly with a code challenge onscreen   
   - Establishes socket connection with Python client
   - Receives OCR processed text from Python client
   - Displays loading state during processing
   - Renders received code solutions with syntax highlighting
   - Manages theme preferences and display settings

3. Subscription Management:
   - Tracks request usage
   - Handles subscription upgrades/downgrades
   - Shows remaining requests for current period

### 2. Firebase Backend Flow
1. Authentication Layer:
   - Validates user credentials
   - Issues authentication tokens
   - Manages session state

2. Data Management:
   - Stores user profiles and preferences
   - Maintains subscription status
   - Records usage history and request counts

3. Access Control:
   - Enforces rate limits (20/month standard, 200/month premium)
   - Validates request authorization
   - Manages API access permissions

4. Storage Operations:
   - Stores processed code solutions
   - Caches frequent requests
   - Manages user history

### 3. Azure Functions Flow
1. Request Processing:
   - Receives OCR text from iOS app via HTTP POST to the `processScreenText` endpoint
   - Validates request parameters (text, userId, language)
   - Creates initial processing record in Firebase
   - Verifies user authentication and subscription status
   - Enforces rate limits based on subscription tier

2. AI Processing with DeepSeek:
   - Implements robust retry mechanism (configurable retries and delays)
   - Rotates through multiple API keys to distribute load and avoid rate limits
   - Formats OCR text with specialized prompting for code challenge extraction
   - Submits to DeepSeek API with language-specific instructions
   - Validates and processes AI responses for errors or successful solutions

3. Response Handling:
   - Formats code solutions for optimal display in the client app
   - Implements detailed error handling with appropriate status codes
   - Stores both successful and error results in Firebase
   - Updates user usage metrics with a retry mechanism
   - Notifies client application through Firebase about new results
   - Returns standardized JSON responses with request status information

4. Diagnostics:
   - Implements comprehensive logging at all processing stages
   - Records detailed information about API requests and responses
   - Tracks performance metrics and error rates
   - Provides a test endpoint (`testFunction`) for verifying service health


### 4. Python Client Flow
1. Image Processing:
   - Captures screenshots of Macbook screen constantly, places inside defined directory
   - Deletes screenshots older than 3 minutes automatically from defined directory
   - when triggered by iOS app, performs OCR on most recent screenshot

2. OCR Operations:
   - Extracts text from image

3. Communication:
   - Establishes socketIO connection with iOS app
   - Sends OCR extracted text to iOS app 

### The entire flow, summarized
1. Initial Setup:
   - User installs iOS app
   - User completes Firebase authentication
   - User's subscription tier is validated
   - Python client is running on user's Macbook
   - Socket connection established between iOS app and Python client

2. Capture & Processing Flow:
   a. Image Capture:
      - Python client continuously captures Macbook screen
      - Screenshots stored in designated directory
      - Old screenshots (>3 min) automatically deleted
   
   b. OCR Processing:
      - User triggers screenshot capture from iOS app
      - Python client selects most recent screenshot
      - OCR processing extracts text from image
      - Extracted text sent to iOS app via socketIO

3. AI Processing Flow:
   a. Request Handling:
      - iOS app sends OCR text to Azure Function
      - Azure validates user authentication
      - Rate limit checked against subscription tier
   
   b. AI Processing:
      - Azure Function formats text for DeepSeek API
      - Request sent to DeepSeek with rotated API keys
      - AI generates code solution
      - Response formatted and optimized

4. Response & Storage Flow:
   a. Data Storage:
      - Formatted solution stored in Firebase
      - Usage metrics updated
      - Request count incremented
   
   b. Client Display:
      - iOS app receives formatted solution
      - Code displayed with syntax highlighting
      - Solution cached for future reference
      - Remaining requests updated in UI

5. Ongoing Operations:
   - Firebase maintains user authentication state
   - Python client continues screenshot monitoring
   - Azure Functions handle concurrent requests
   - Usage metrics tracked and updated
   - Rate limits enforced per subscription tier



