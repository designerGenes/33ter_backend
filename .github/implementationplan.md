## Application Overview
33ter is a mobile application that helps developers solve coding problems by capturing code snippets through OCR, processing them with AI, and presenting formatted solutions.


## Detailed Application Flow

### 1. iOS Client Flow (Mobile App)
1. User Authentication:
   - Handle user login/registration via Firebase Auth SDK (`/iOS/33ter/Services/AuthService.swift`)
   - Validate subscription status using `UserSubscription` model
   - Cache authentication tokens in `KeychainManager`

2. Main Application Flow:
   - User triggers screenshot via `CaptureButton` in `MainView.swift`
   - Establishes socket connection through `SocketIOManager.swift` to Python client
   - Receives OCR processed text from Python client in `ScreenCaptureViewModel`
   - Displays loading state using `LoadingIndicatorView.swift`
   - Renders received code solutions with syntax highlighting using `CodeHighlighter.swift`
   - Manages theme preferences using `ThemeManager.swift` supporting light/dark modes
   - Uses `UserDefaults` for persistent settings storage

3. Subscription Management:
   - Tracks request usage in `RequestCounter` class
   - Handles subscription upgrades/downgrades via `SubscriptionService.swift`
   - Shows remaining requests using `UsageStatusView.swift`
   - Implements `InAppPurchaseManager` for payment processing

### 2. Firebase Backend Flow
1. Authentication Layer:
   - Validates user credentials via Firebase Authentication
   - Issues JWT authentication tokens with custom claims
   - Manages session state in Firestore `/users/{userId}/sessions`

2. Data Management:
   - Stores user profiles in Firestore collection `/users`
   - Maintains subscription status in `/users/{userId}/subscription`
   - Records usage history in `/users/{userId}/requests`
   - Request counts tracked in `/users/{userId}/metrics`
   - Schema defined in `firebase-schema.json`

3. Access Control:
   - Enforces rate limits using Firestore triggers
   - Validates request authorization using Firebase Auth middleware
   - Manages API access permissions with custom claims
   - Security rules defined in `firestore.rules`

4. Storage Operations:
   - Stores processed code solutions in `/users/{userId}/solutions`
   - Caches frequent requests in Firebase caching layer
   - Manages user history with TTL settings

### 3. Azure Functions Flow
1. Request Processing:
   - Receives OCR text from iOS app via HTTP POST to the `/api/processScreenText` endpoint
   - Validates request parameters using `RequestValidator` class
   - Creates initial processing record in Firebase using `FirebaseService.createRequest()`
   - Verifies user authentication using `FirebaseAuth.verifyToken()`
   - Enforces rate limits based on subscription tier using `UsageLimiter.checkLimit()`

2. AI Processing with DeepSeek:
   - Implements robust retry mechanism in `RetryHandler.js` (configurable retries and delays)
   - Rotates through multiple API keys using `ApiKeyRotator.js`
   - Formats OCR text with specialized prompting using `PromptFormatter.js`
   - Submits to DeepSeek API with language-specific instructions using `DeepSeekClient.js`
   - Validates responses with `ResponseValidator.js`
   - Handles API rate limits via exponential backoff in `BackoffStrategy.js`

3. Response Handling:
   - Formats code solutions using `SolutionFormatter.js`
   - Implements error handling with `ErrorHandler.js` providing detailed status codes
   - Stores results in Firebase using transactional writes
   - Updates user metrics with `UsageTracker.js` (includes retry mechanism)
   - Returns standardized JSON responses conforming to `ResponseSchema.json`
   - Includes request correlation IDs for traceability

4. Diagnostics:
   - Logs using structured logging in `Logger.js`
   - Records API request metrics in Application Insights
   - Implements custom telemetry using `TelemetryClient.js`
   - Exports performance data to monitoring dashboards
   - Provides health checks via `/api/testFunction` endpoint

### 4. Python Client Flow (this app)
1. Image Processing:
   - Captures screenshots 
   - Uses `pyautogui` for screen capture at configurable intervals
   - Stores images in `/tmp/33ter/screenshots` with timestamp naming
   - `ImageCleaner` thread removes old screenshots based on configurable TTL
   - Supports multiple display configurations with `DisplayDetector` class

2. OCR Operations:
   - `OCRProcessor` uses Tesseract or EasyOCR backends (configurable)
   - Applies image preprocessing with `ImageEnhancer` for improved accuracy
   - Supports language detection with `LanguageDetector`
   - Implements heuristics for code block detection in `CodeBlockExtractor`
   - Caches OCR results with `LRUCache` to avoid duplicate processing

3. Communication:
   - `SocketServer` uses python-socketio on port 33333
   - Implements event handlers for 'connect', 'disconnect', 'capture_request'
   - Uses authentication middleware with `SocketAuthenticator`
   - Sends OCR extracted text via 'ocr_result' event with JSON payload
   - Provides status updates via 'processing_status' events

### The entire flow, summarized
1. Initial Setup:
   - User installs iOS app from App Store
   - User completes Firebase authentication via `AuthViewController`
   - User's subscription tier is validated against Firebase `/users/{userId}/subscription`
   - Python client (`server.py`) is running on user's Macbook as background service
   - Socket connection established between iOS app and Python client at `localhost:33333`

2. Capture & Processing Flow:
   a. Image Capture:
      - Python `ScreenshotManager` continuously captures Macbook screen every 2 seconds
      - Screenshots stored in `/tmp/33ter/screenshots/{timestamp}.png`
      - `ImageCleaner` removes screenshots older than 3 minutes
      - Configuration variables controlled via `config.py`
   
   b. OCR Processing:
      - User triggers capture via `CaptureButtonView.swift`
      - iOS app emits 'capture_request' event through SocketIO
      - Python client selects most recent screenshot from `/tmp/33ter/screenshots/`
      - `OCRProcessor` extracts text with configurable confidence threshold
      - Extracted text sent to iOS app via 'ocr_result' SocketIO event with JSON payload:
        ```json
        {
          "text": "extracted code text",
          "confidence": 0.92,
          "timestamp": "2023-07-01T12:34:56Z",
          "source_image": "screenshot_20230701123456.png"
        }
        ```

3. AI Processing Flow:
   a. Request Handling:
      - iOS `ApiService.swift` sends OCR text to Azure Function
      - `RequestProcessor.js` validates input structure
      - `FirebaseAuthenticator.js` verifies Firebase JWT token
      - `RateLimiter.js` checks usage against subscription tier limits
   
   b. AI Processing:
      - `PromptBuilder.js` formats text for DeepSeek API with specific instructions
      - Request sent to DeepSeek with rotating API keys from `ApiKeyManager.js`
      - AI generates code solution with language-specific formatting
      - Response processed through `OutputFormatter.js` for consistent structure
      - Response structure follows `SolutionSchema.json` format

4. Response & Storage Flow:
   a. Data Storage:
      - Formatted solution stored in Firebase `/users/{userId}/solutions/{solutionId}`
      - Usage metrics updated via atomic transaction in `/users/{userId}/metrics`
      - Request count incremented with timestamp and solution reference
      - Solution data structure:
        ```json
        {
          "original_text": "OCR extracted text",
          "solution": "AI generated solution",
          "language": "detected programming language",
          "created_at": "ISO timestamp",
          "processing_time_ms": 1243,
          "confidence_score": 0.95
        }
        ```
   
   b. Client Display:
      - iOS app receives formatted solution in `SolutionResponse` model
      - `SolutionDisplayController` renders with syntax highlighting via `HighlightJS`
      - Solution cached in `CoreDataManager` for offline access
      - `UsageViewController` updates remaining requests count
      - `CodeHistoryManager` adds entry to solution history

5. Ongoing Operations:
   - Firebase maintains user session with refresh tokens
   - Python client continues screenshot monitoring via background thread
   - `MetricsCollector.js` in Azure Functions tracks system performance
   - `UsageAnalytics.swift` reports anonymous usage statistics
   - Rate limits enforced based on subscription tier settings in `subscription_tiers.json`

## Environment Configuration

### Python Client
- Required dependencies in `app/requirements.txt`
- Configuration in `/app/config.py` with overrides via environment variables
- Runtime logs stored in `/var/log/33ter/`
- Supports macOS versions 10.15+

### Azure Functions
- Node.js v16+ runtime
- Dependencies in `functions/package.json`
- Local settings in `functions/local.settings.json`
- Production configuration via Application Settings in Azure Portal
- Logging level controlled via `FUNCTIONS_LOG_LEVEL` environment variable

### iOS Client
- SwiftUI iOS 15.0+ target
- Dependencies managed via Swift Package Manager
- Environment configuration in `Config.xcconfig`
- Debug/Release build configurations with different Firebase instances
- Localization support for English, Spanish, and Chinese




# Implementation Plan for iOSReceiver App

This document serves as a blueprint for updating our iOSReceiver app to incorporate functionalities introduced in the TestApp. The plan includes overhauling the use of Firestore and integrating Firebase Realtime Database alongside it. The steps outlined will guide the transition, ensuring seamless integration and maintaining existing functionalities.

1. **Integration Plan: Firebase Realtime Database from TestApp to iOS Receiver**

    **Major Step 1: Add Firebase Realtime Database Support**
    - **Minor Steps:**
      - Update Firebase Dependencies
         - `Package.swift` - Add Firebase Realtime Database dependency
         - `FirebaseApp.configure()` call location - Ensure proper initialization
         - Import statements across relevant files
      - Initialize Realtime Database
         - `AppDelegate.swift` or `App.swift` - Add initialization code
         - `FirebaseConfiguration` - Update to include RTDB configuration
         - Add database persistence configuration for offline capability
      - Create RTDB Service Layer
         - Create new `RealtimeDatabaseService.swift` file with core functionality
         - Add `DatabaseReference` management functions
         - Implement `RealtimeDatabaseError` enum for error handling
      - Add Database Transaction Utilities
         - Create `DatabaseTransaction.swift` for atomic operations
         - Implement JSON serialization/deserialization helpers
         - Add transaction retry mechanism
    - **Achievement:** Establishes the foundation for Firebase Realtime Database integration while maintaining existing Firestore functionality, enabling the app to connect to both databases simultaneously.

    **Major Step 2: Authentication Integration for RTDB**
    - **Minor Steps:**
      - Extend Authentication Service
         - Update `AuthService.swift` to handle RTDB authentication
         - Modify `signIn(email:password:)` to authenticate with both databases
         - Add `authenticateRealtimeDatabase()` function
      - Create User-specific Database References
         - Create `UserDatabaseManager.swift` to handle user paths
         - Implement `getResultsReference(for userId:)` function
         - Add path constants for standardized database locations
      - Implement Auth State Monitoring
         - Add `DatabaseAuthStateListener` protocol
         - Create `reauthorizeIfNeeded()` function for token refreshing
         - Implement connection state monitoring
    - **Achievement:** Ensures that the app maintains proper authentication with the Realtime Database, creating proper user-specific references that maintain security and follow Firebase best practices.

    **Major Step 3: Implement Azure Function Communication**
    - **Minor Steps:**
      - Create Request/Response Models
         - Create `AzureFunctionRequest.swift` model
         - Implement `RequestStatus` enum for tracking states
         - Add `RequestIDGenerator` utility class
      - Implement API Service
         - Create `AzureFunctionService.swift` service
         - Implement `submitCodeRequest(text:completion:)` function
         - Add `handleAPIResponse(data:response:error:)` handler
      - Add Error Handling
         - Create `AzureFunctionError` enum
         - Implement `RetryHandler` for failed requests
         - Add request timeout and connectivity monitoring
      - Implement Request Tracking
         - Create `RequestTracker.swift` to manage pending requests
         - Add `trackRequest(id:)` and `completeRequest(id:)` functions
         - Implement request timeout monitoring
    - **Achievement:** Enables the app to communicate with Azure Functions for code processing, with proper request generation, error handling, and tracking mechanisms that match the TestApp implementation.

    **Major Step 4: Implement Realtime Database Listeners**
    - **Minor Steps:**
      - Create Observer Pattern
         - Create `DatabaseObserver` protocol
         - Implement `ResultsListener` class
         - Add `ListenerRegistration` management system
      - Implement Request-specific Listeners
         - Create `addListener(for requestId:userId:completion:)` function
         - Implement `ListenerStateManager` for multiple listeners
         - Add `removeListener(for requestId:)` cleanup function
      - Create Data Processing
         - Implement `ResultDataProcessor` class
         - Create `CodeSolutionMapper` for data conversion
         - Add `DatabaseValueTransformer` for type safety
      - Add Connection State Handling
         - Implement `.info/connected` observer
         - Add reconnection logic and offline capabilities
         - Create connection state notifications
    - **Achievement:** Creates a robust system for listening to specific paths in the Realtime Database where Azure Functions will write code solutions, with proper error handling and state management.

    **Major Step 5: Connect to Existing UI Components**
    - **Minor Steps:**
      - Update View Models
         - Modify `ContentViewModel` to handle RTDB results
         - Update state management for processing states
         - Create `ResultPresenter` to format responses
      - Connect to `CodeBlockView`
         - Create adapter between RTDB data and `CodeBlockView` format
         - Add language detection for proper syntax highlighting
         - Implement automatic theme selection based on code type
      - Add Loading and Error States
         - Implement `ProcessingIndicatorView` for request status
         - Create error handling UI components
         - Add retry functionality for failed requests
      - Implement Result Display Logic
         - Update `ScrollView` management in main screen
         - Add animation for new results appearance
         - Implement result caching for offline viewing
    - **Achievement:** Completes the integration by connecting the Realtime Database results to the existing UI components, particularly the `CodeBlockView` that's already implemented, creating a seamless user experience.


