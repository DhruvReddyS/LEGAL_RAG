# Interview Preparation Document

This document is written from the project plan and architecture reference, not as a celebration of every line of code. It is meant to help explain the system clearly in an interview, especially the product idea, the planned modules, the main architecture, and the interview concepts behind them.

Important note:
- This project is not a classic MERN app.
- The frontend is React/Next.js.
- The backend is FastAPI/Python with PostgreSQL, Qdrant, and MinIO.
- MongoDB is not the primary database in this codebase, but MERN interviewers may still ask MongoDB questions, so the Mongo section later explains the concepts you should know and how they compare with PostgreSQL.

---

## 1. Project Understanding

### 1.1 Simple explanation

The project is a legal decision-support platform. A user asks a legal question, and the system tries to answer using verified legal sources from a curated corpus. It is designed for different user types:
- citizens who need plain-language legal help,
- police who need investigation and procedure support,
- advocates who need legal strategy and authority research,
- admins who manage the corpus and platform.

The main idea is: do not guess, do not hallucinate, and do not answer unless the source material supports the answer.

### 1.2 Technical explanation

The system is a retrieval-augmented generation platform with multi-role workflows and safety gates. Instead of relying on a model alone, it:
1. screens the query for safety,
2. decides whether the question should use a fast retrieval-only lane or a deeper agentic lane,
3. searches a curated legal corpus,
4. verifies claims against evidence,
5. publishes only supported claims with citations,
6. abstains when evidence is insufficient.

### 1.3 Project overview and problem statement

The project solves a real legal-research problem:
- legal text is difficult to read,
- law changes over time,
- different users need different kinds of answers,
- hallucinated legal answers can be harmful,
- private case evidence must stay isolated.

The project’s core challenge is to provide useful answers while remaining grounded, current, and safe.

### 1.4 Purpose and target users

Target users:
- Citizen: asks legal questions in simple language.
- Police: uses it for investigation workflow, deadlines, evidence, and FIR drafting.
- Advocate: uses it for two-sided legal argumentation, adverse authority, and case strategy.
- Admin: manages users, corpus stats, audit logs, and ingestion progress.

### 1.5 Complete feature/module list

Planned and/or implemented major modules:
- Authentication and session management
- Role-based dashboards
- Citizen legal Q&A
- Police investigation workspace
- Advocate case strategy workspace
- Admin control plane
- Chat history
- Case creation and case-scoped evidence
- Document upload and analysis
- Retrieval search
- Fast evidence answer lane
- Deep reasoning lane
- Answer verification and publication gate
- Authority and citation currency checks
- Investigation timelines and compliance checks
- Corpus ingestion and indexing
- Feedback system
- Audit logging
- Health/readiness checks

### 1.6 How every major feature is implemented

High level:
- Frontend collects user input and shows workspace-specific UI.
- API routes receive the request.
- Service layer applies business rules.
- Database stores auth, chats, cases, jobs, and audit data.
- Retrieval layer searches legal corpus.
- Agent layer reasons over retrieved evidence.
- Verification layer checks claims before publishing.

### 1.7 End-to-end workflows

Typical flow:
1. User signs in.
2. Frontend restores session and role.
3. User asks a question or opens a workspace.
4. Frontend sends request to backend.
5. Backend checks auth, role, case scope, and safety.
6. Retrieval fetches evidence from the corpus.
7. Deep lane may generate claims and verify them.
8. Backend returns citations, answer text, confidence labels, or abstention.
9. Frontend renders the result with loading, error, and citation UI.

### 1.8 User roles and permissions

Role summary:
- citizen: read corpus, ask public-law questions
- police: read corpus, manage own cases, upload evidence, draft FIRs, view timelines
- advocate: read corpus, manage own cases, upload client evidence, run defence analysis
- admin: read corpus, manage users, monitor the system, inspect corpus stats

The important interview point:
- permissions are not just UI-level checks,
- they are enforced on the backend,
- private case data is isolated by ownership and scope.

### 1.9 Important business logic

Key business rules:
- Do not answer if evidence is insufficient.
- Do not publish unsupported claims.
- Do not treat unverified law as current.
- Repealed law must be labeled clearly.
- Private case data must never leak across users.
- Police and advocate case data are separate from general corpus search.
- Admins do not get blanket access to private case search.

---

## 2. Project Architecture

### 2.1 Simple explanation

Think of the system as four layers:
- React frontend for the interface
- FastAPI backend for logic and APIs
- PostgreSQL for app data
- Qdrant and object storage for corpus search and files

### 2.2 Overall system architecture

```text
User
  |
  v
React/Next.js Frontend
  |
  v
FastAPI Backend
  |         |            |
  |         |            +--> PostgreSQL (users, cases, chats, jobs, audit)
  |         +--> Qdrant (vector search / retrieval)
  +--> MinIO/S3 (documents, uploads, generated files)
  |
  +--> Ollama / LLM for deep reasoning
```

### 2.3 Frontend architecture

Frontend is organized around:
- role-aware home page
- reusable workspace components
- chat UI
- auth modal
- document and evidence tools
- admin workspace
- professional workspace for police and advocates

Important frontend files:
- `frontend/app/page.tsx`
- `frontend/components/ProfessionalWorkspace.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `frontend/lib/answer-presentation.ts`
- `frontend/lib/investigation-presentation.ts`
- `frontend/components/AuthModal.tsx`
- `frontend/components/ChatInput.tsx`

### 2.4 Backend architecture

Backend is layered:
- routers: HTTP endpoints
- services: business logic
- agents: multi-step legal reasoning
- models: database entities
- schemas: request/response validation
- ingestion: corpus build/index pipeline
- core: config, auth, db, security

Important backend files:
- `backend/main.py`
- `backend/app/routers/*.py`
- `backend/app/services/*.py`
- `backend/app/agents/*.py`
- `backend/app/models/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/*.py`

### 2.5 Database architecture

Primary relational database: PostgreSQL.

Stores:
- users
- roles and permissions
- sessions/tokens
- cases
- case documents
- chats
- jobs
- audit logs
- investigation facts and timelines

Corpus search is not stored in PostgreSQL alone. Search vectors and metadata are indexed in Qdrant, while source files live in object storage.

### 2.6 API architecture

API style:
- REST-style HTTP endpoints
- JSON request/response bodies
- cookie-based auth support
- role-based and case-based authorization
- separate endpoints for chat, cases, documents, admin, ingestion, retrieval, feedback, and jobs

### 2.7 Authentication and authorization architecture

Authentication:
- JWT access token
- JWT refresh token
- refresh token rotation
- revocation on reuse detection
- cookie-based session support in frontend

Authorization:
- role-based access control
- case ownership checks
- private corpus isolation
- structural checks in sensitive routes

### 2.8 Data flow between components

```text
UI event -> API request -> router -> service -> DB/Qdrant/LLM -> business rule check -> response -> UI render
```

### 2.9 Request-response lifecycle

Example lifecycle for chat:
1. User types a question.
2. React sends `/chat/query`.
3. FastAPI reads user/session/case context.
4. Safety and routing decide fast vs deep lane.
5. Retrieval fetches legal evidence.
6. Reasoning and verification may run.
7. Backend returns answer or abstention.
8. Frontend stores and renders the conversation.

### 2.10 Folder/codebase structure

From the repository:
- `frontend/` UI
- `backend/` API and business logic
- `docker/` local stack
- `scripts/` corpus and operational tooling
- `docs/` PRD, operations, next steps, evidence
- `data/legal_kb/` corpus and metadata

### 2.11 Architecture and design decisions

Why this architecture:
- FastAPI for fast async APIs and clean validation
- PostgreSQL for durable relational app state
- Qdrant for vector search and hybrid retrieval
- object storage for large files and uploads
- role-based workspaces to keep user journeys focused
- claim verification before publication to reduce hallucinations
- separate fast and deep lanes for performance and quality balance

---

## 3. Feature Implementation

This section explains important features in the order a request travels.

### 3.1 Authentication

Frontend:
- login/register UI
- session restoration on load
- cookie-aware API helper

API:
- `/auth/login`
- `/auth/register`
- `/auth/refresh`
- `/auth/me`
- cookie-based versions too

Backend logic:
- password verification
- JWT creation
- refresh token rotation
- audit logging
- login throttling

Database:
- user table
- token revocation records
- audit logs

UI:
- user is redirected into the correct role workspace after auth

### 3.2 Citizen chat

Frontend:
- question input
- response mode selection
- history panel
- loading and stop controls

API:
- `/chat/query`
- `/chat/sessions`
- `/feedback`

Backend:
- safety screening
- routing to fast/deep lane
- retrieval
- claim verification
- response formatting

Database:
- chat sessions
- chat messages
- feedback records

### 3.3 Police workspace

Frontend:
- case list
- case file
- evidence upload
- FIR draft
- investigation deadlines
- compliance checklist
- citation checks

API:
- `cases`
- `documents`
- `strategy`
- `citizen-intake`
- `investigation`
- `retrieval`

Backend:
- create and update case
- upload and index evidence
- draft FIR from facts
- compute timelines
- compute BNSS compliance

Database:
- cases
- documents
- generated drafts
- investigation facts

### 3.4 Advocate workspace

Frontend:
- case list
- client evidence
- authority research
- defence analysis
- case search

Backend:
- case-scoped retrieval
- two-sided strategy output
- adverse authority handling
- citation currency check

Business logic:
- reject unsupported or unsafe tactics
- keep client evidence isolated

### 3.5 Admin workspace

Frontend:
- user management
- corpus stats
- ingestion progress
- audit log

Backend:
- admin overview endpoints
- user administration
- corpus monitoring

### 3.6 Document upload and analysis

Frontend:
- file picker / upload dialog
- document analyzer workspace

Backend:
- store file in object storage
- extract text
- index into search pipeline
- show page/chunk counts

### 3.7 Retrieval and evidence search

Frontend:
- user enters query
- results show citations and answer fragments

Backend:
- query normalization
- hybrid vector + lexical search
- filtering by role/case/corpus tier
- citation following
- currency labelling

### 3.8 Deep review jobs

Frontend:
- long-running work can be stopped or polled

Backend:
- create durable job
- worker claims job
- progress can be checked

Database:
- job state table

---

## 4. Frontend

### 4.1 React architecture

The frontend uses React components with state-driven rendering. The page is split into:
- top-level page controller
- reusable workspace components
- dialogs and overlays
- small helper components for message rendering, uploads, logo, etc.

### 4.2 Components and reusable components

Key patterns:
- `HomePage` as the main orchestrator
- `ProfessionalWorkspace` for police/advocate flows
- `MessageBubble` for chat rendering
- `ChatInput` for query entry
- `AuthModal` for login/register
- `AdminWorkspace` for admin operations

### 4.3 Props and state

The app uses React state heavily for:
- user session
- active chat
- case selection
- theme
- loading state
- history
- current workspace view

Interview point:
- local UI state handles ephemeral interactions,
- backend handles persistent business data.

### 4.4 Hooks

Important hooks used:
- `useState`
- `useEffect`
- `useMemo`
- `useRef`

Why they matter:
- `useEffect` restores auth and loads data
- `useMemo` avoids recalculating derived view data
- `useRef` tracks active requests and scroll targets

### 4.5 Forms and validation

Frontend validation examples:
- require non-empty query
- require minimum case title length
- require a selected case for case-scoped actions
- prevent invalid upload actions

### 4.6 Routing

The app is primarily a single-page interface with internal state-based view switching, not a traditional multi-page React Router app.

### 4.7 Protected routes

Protection happens mostly through:
- auth restoration
- conditional UI rendering
- backend authorization enforcement

### 4.8 State management

The app does not use Redux for core state.
It relies on:
- component state
- derived state
- server-backed data loading
- session-based preference storage

### 4.9 API integration

All API calls are centralized in `frontend/lib/api.ts`.

Benefits:
- one place for request headers and credentials
- retry refresh logic
- consistent error handling
- cleaner feature components

### 4.10 Authentication handling

Auth flow:
- sign in/out via cookie-aware API
- refresh session on page load
- keep user in memory for current session
- use protected backend endpoints for true security

### 4.11 Error/loading handling

Common patterns:
- loading spinners
- disabled buttons during requests
- inline error banners
- fallback states when data is unavailable
- aborting requests when user stops a long operation

### 4.12 Important JavaScript concepts used in frontend

Key concepts to mention:
- async/await
- promises
- abort controllers
- object spread
- array mapping/filtering
- optional chaining
- null handling
- controlled components
- event handling

---

## 5. Backend

### 5.1 Node.js fundamentals relevant to the project

This project’s backend is not Node.js, but an interviewer may still ask Node-style backend questions. The relevant concepts are:
- async I/O
- request lifecycle
- middleware
- environment variables
- routing
- error handling
- authentication

### 5.2 Express architecture

The project uses FastAPI instead of Express, but the mental model is similar:
- routes map URL paths to handlers
- middleware runs before/after handlers
- services contain business logic
- schemas validate input/output

### 5.3 Routes

Major route groups:
- auth
- chat
- cases
- documents
- strategy
- retrieval
- admin
- ingestion
- storage
- jobs
- feedback
- investigation
- citizen intake

### 5.4 Controllers

In FastAPI, route functions act like controllers. They:
- read request data
- call services
- handle errors
- return typed responses

### 5.5 Services

Service layer responsibilities:
- auth
- rate limiting
- retrieval
- job orchestration
- token revocation
- document handling
- safety screening
- legal reasoning helpers
- investigation logic

### 5.6 Middleware

Important middleware:
- CORS
- trusted host checks
- desktop origin security
- request telemetry

### 5.7 Models and repositories

Models represent database rows such as:
- users
- chats
- cases
- audit logs
- tokens
- jobs

Repository-style access happens through SQLAlchemy sessions and query logic in services.

### 5.8 REST APIs

The system mostly follows REST semantics:
- GET for read
- POST for create or action
- PATCH/PUT for updates
- 401/403/404/409/429/503 used meaningfully

### 5.9 Request/response handling

Backend flow:
- validate request body
- enforce auth
- enforce role/case scope
- execute business logic
- return structured JSON

### 5.10 Authentication

Backend auth uses:
- JWT access tokens
- refresh tokens
- cookie transport
- token reuse detection

### 5.11 Authorization/RBAC

RBAC checks:
- role determines accessible actions
- case ownership determines private evidence access
- admin privileges are not equivalent to unrestricted private search

### 5.12 Validation

Validation is done through schemas and route logic.
Examples:
- email/password format
- role restrictions on registration
- case existence
- required case scope
- query structure for chat and search

### 5.13 Error handling

Design principle:
- fail closed, not open
- hide unnecessary internal details
- return 503 for dependency outages
- return 404 for unauthorized case existence checks when appropriate

### 5.14 Async operations

Used for:
- API handlers
- database operations
- retrieval
- job polling
- file processing

### 5.15 Configuration management

Configuration comes from environment variables and settings.
Important interview point:
- do not hardcode secrets
- keep host-specific configuration separate from container configuration

### 5.16 Security

Security themes:
- cookie security
- token revocation
- rate limiting
- host/CORS restrictions
- request telemetry without leaking user content
- private corpus isolation

### 5.17 Important backend design patterns

Patterns used:
- router-service separation
- async service layer
- typed schema validation
- claim verification before publishing
- job worker for long-running tasks
- deterministic helpers for legal labels and currency

---

## 6. PostgreSQL & Database

### 6.1 Simple explanation

PostgreSQL is the system’s main structured database. It stores who the users are, what cases exist, what chats happened, and what jobs and audit events were recorded.

### 6.2 Complete database design/schema

Likely major tables:
- users
- roles
- permissions
- refresh token revocation
- cases
- case documents
- chats
- chat messages
- feedback
- jobs
- audit logs
- investigation facts
- timeline entries

### 6.3 Tables and relationships

Typical relationships:
- one user can own many cases
- one case can have many documents
- one chat session can have many messages
- one user can have many audit events
- one job can belong to one request or workflow

### 6.4 Primary/foreign keys

Use primary keys for unique identity.
Use foreign keys for:
- user to case
- case to documents
- session to messages
- job to owner/request context

### 6.5 CRUD operations

Examples:
- create user on registration
- read current user on `/auth/me`
- update case title/status
- delete or revoke sessions/tokens
- insert feedback or audit records

### 6.6 SQL queries

You should be ready to explain:
- select with filters
- joins across users/cases/messages
- pagination
- ordering by updated time
- access checks in query filters

### 6.7 JOINs

Common join idea:
- load case list with owner information
- load messages with session metadata
- load audit history with user context

### 6.8 Constraints

Useful constraints:
- unique email
- non-null ownership fields
- foreign key integrity
- case scope consistency

### 6.9 Indexes

Indexes matter for:
- email lookup
- case lookup
- chat/session history
- audit filtering
- job polling

### 6.10 Normalization

Good normalization examples:
- separate users from cases
- separate chat sessions from messages
- separate tokens from users
- separate audit events from business objects

### 6.11 Transactions and ACID

Use transactions when:
- creating user + audit log
- rotating refresh tokens
- changing case status and related metadata
- ingesting and recording documents consistently

### 6.12 Connection pooling

The backend uses an async SQLAlchemy engine with pooling. This prevents opening a brand-new database connection for every request.

### 6.13 Database security

Security practices:
- parameterized queries through ORM
- ownership checks
- no direct public access to private case data
- minimal sensitive data in logs

### 6.14 How Node/Express would communicate with PostgreSQL

Even though this project does not use Node for the backend, in a MERN interview you can explain:
- Express route receives request
- service queries PostgreSQL using an ORM/query builder
- database returns rows
- service formats response

### 6.15 Important SQL/PostgreSQL interview concepts

Know these:
- primary key, foreign key
- join
- index
- transaction
- ACID
- normalization
- isolation level
- connection pooling
- unique constraint
- cascade behavior

---

## 7. MongoDB

### 7.1 Why this section matters

The project itself is PostgreSQL-based, but if the interview says “MERN,” you still need to explain MongoDB clearly.

### 7.2 MongoDB fundamentals

MongoDB is a NoSQL document database. Data is stored in collections of JSON-like documents.

### 7.3 Documents/collections

- collection = table-like grouping
- document = row-like JSON object

### 7.4 CRUD

- create document
- read document
- update document
- delete document

### 7.5 Mongoose

Mongoose is an ODM for MongoDB.
It gives:
- schemas
- validation
- models
- middleware/hooks

### 7.6 Relationships

MongoDB relationships are often handled by:
- embedding
- referencing

### 7.7 MongoDB vs PostgreSQL

MongoDB:
- flexible schema
- document-oriented
- good for rapidly changing nested data

PostgreSQL:
- strict relational structure
- strong joins and constraints
- excellent for transactional data

### 7.8 When and why each should be used

Use MongoDB when:
- schema changes often
- documents are naturally nested
- you want fast iteration on flexible data

Use PostgreSQL when:
- relationships matter
- consistency matters
- transactions matter
- reporting and joins matter

For this project, PostgreSQL is a better fit for auth, cases, chats, jobs, and audit logs.

---

## 8. Core MERN Concepts

### 8.1 JavaScript

Important concepts:
- variables, scope, closures
- arrays and objects
- async/await
- promises
- modules
- destructuring
- spread/rest

### 8.2 React

Know:
- components
- props
- state
- lifecycle via hooks
- controlled inputs
- conditional rendering
- lists and keys
- data fetching in effects

### 8.3 Node.js

Know:
- event loop
- non-blocking I/O
- modules
- environment variables
- file and network I/O

### 8.4 Express.js

Know:
- routes
- middleware
- request/response objects
- status codes
- error handlers

### 8.5 MongoDB

Know:
- collections
- documents
- flexible schema
- indexing
- Mongoose

### 8.6 REST APIs

Know:
- resource-based URLs
- HTTP methods
- JSON payloads
- status codes
- idempotency basics

### 8.7 HTTP

Know:
- request/response cycle
- headers
- cookies
- CORS
- caching basics

### 8.8 Async programming

Know:
- callbacks
- promises
- async/await
- concurrency vs parallelism

### 8.9 Event loop

Explain simply:
- Node.js can handle many requests without blocking because the event loop schedules asynchronous work.

### 8.10 Middleware

Middleware is code that runs between request and response.
Examples:
- auth
- logging
- CORS
- validation

### 8.11 JWT

JWT is a signed token used to prove identity.
In this project, JWT is used for session auth and refresh flows.

### 8.12 bcrypt

bcrypt hashes passwords securely so the server does not store plain text passwords.

### 8.13 CORS

CORS controls which frontends can call the backend from a browser.

### 8.14 Authentication vs authorization

- Authentication = who are you?
- Authorization = what can you do?

### 8.15 Security

Security concepts to mention:
- password hashing
- token rotation
- rate limiting
- request validation
- case isolation
- least privilege

---

## 9. Complete End-to-End Flows

### 9.1 Login flow

```text
User enters email/password
-> frontend sends auth request
-> backend validates credentials
-> backend issues JWTs/cookies
-> frontend restores session
-> workspace loads based on role
```

### 9.2 Citizen legal question flow

```text
User asks question
-> frontend sends /chat/query
-> backend safety screen runs
-> router selects fast or deep lane
-> retrieval searches legal corpus
-> reasoning/verification may run
-> backend returns citations or abstention
-> frontend renders answer
```

### 9.3 Police evidence upload flow

```text
Officer creates/opens case
-> uploads file
-> file stored in object storage
-> text extracted
-> case evidence indexed
-> document analyzer reads the upload
-> case workspace refreshes
```

### 9.4 FIR drafting flow

```text
Police enters facts
-> backend validates case scope
-> relevant legal provisions are retrieved
-> drafting agent produces structured FIR draft
-> user reviews immutable draft
```

### 9.5 Advocate defence analysis flow

```text
Advocate enters scenario
-> backend checks case ownership
-> retrieval fetches authority and evidence
-> strategy agent produces two-sided analysis
-> unsupported points are rejected
```

### 9.6 Admin management flow

```text
Admin opens dashboard
-> frontend calls admin endpoints
-> backend checks admin permission
-> system returns user/corpus/job/audit info
```

### 9.7 Request-response lifecycle diagram

```text
Browser action
  -> React state update
  -> fetch call
  -> FastAPI route
  -> auth/security check
  -> business service
  -> PostgreSQL/Qdrant/LLM
  -> response JSON
  -> UI update
```

---

## 10. Engineering Concepts

### 10.1 API design

Good API traits in this project:
- clear resource naming
- role-aware endpoints
- consistent JSON
- proper status codes
- minimal leakage in errors

### 10.2 Database design

Good design traits:
- normalized app data
- separate relational and vector storage
- ownership columns on sensitive resources
- audit support

### 10.3 Security

Security choices:
- secure cookies
- refresh rotation
- backend ownership enforcement
- no open private search
- request telemetry without content logging

### 10.4 Performance

Performance strategies:
- fast lane avoids unnecessary LLM calls
- query caching
- async API
- durable jobs for long work
- vector search instead of full-text only

### 10.5 Scalability

Scalability ideas:
- separate services by responsibility
- worker for long jobs
- indexed search
- pagination on lists
- role-based UI to limit unnecessary data

### 10.6 Error handling

Approach:
- return meaningful status codes
- use fallbacks where safe
- fail closed when uncertain

### 10.7 Validation

Validation exists in:
- frontend forms
- backend schemas
- service logic
- security filters

### 10.8 Logging

Logs should contain:
- request IDs
- operation status
- timings
- errors without exposing sensitive content

### 10.9 Testing

Good testing areas:
- auth
- authorization
- case isolation
- retrieval quality
- answer quality
- frontend rendering and behavior

### 10.10 Deployment

Deployment includes:
- local backend
- frontend app
- database
- vector store
- object store
- environment configuration

### 10.11 Environment variables

Use env vars for:
- DB URL
- API URL
- auth secrets
- model settings
- storage endpoints

### 10.12 Git/version control

Be ready to talk about:
- branches for features
- migrations
- commit history
- avoiding secrets in git

### 10.13 Common bugs/challenges and solutions

Possible issues:
- token refresh loops
- stale session state
- private data leakage
- query answers not reaching governing provision
- wrong currency labels
- long-running jobs timing out

### 10.14 Possible project improvements

Good improvement ideas:
- better citizen readability
- more provision-reach bridges
- broader advocate evaluation set
- additional explainability in citations
- better progress UI for deep jobs

---

## 11. Project Interview Preparation

### 11.1 How to explain the project

Simple version:
“I built a legal decision-support platform that answers questions using a curated legal corpus. It supports different roles like citizen, police, advocate, and admin. The key design goal is to stay grounded in evidence, not hallucinate, and isolate private case data.”

Technical version:
“It is a multi-role retrieval-augmented system built with a React frontend, FastAPI backend, PostgreSQL for app data, Qdrant for hybrid retrieval, and a verification pipeline that only publishes claims supported by retrieved evidence.”

### 11.2 Architecture questions

Be ready to explain:
- why PostgreSQL was chosen for core app data
- why Qdrant was used for retrieval
- why role-based workspaces were needed
- why the system has fast and deep lanes
- why verification happens before publication

### 11.3 Major feature questions

For each feature, explain:
- what it does,
- who uses it,
- what data it needs,
- how backend authorization works,
- how the UI reflects the backend result.

### 11.4 Implementation decisions

Examples:
- “I separated chat, case, and admin flows because each role needs a different interaction model.”
- “I used a fast lane for retrieval-only answers so simple questions do not pay the cost of the deep agent graph.”
- “I used ownership checks in the backend so UI hiding alone cannot protect private case data.”

### 11.5 Tech-stack decisions

Why this stack works:
- React for fast interactive UI
- FastAPI for typed async APIs
- PostgreSQL for durable relational data
- Qdrant for legal corpus search
- object storage for files
- LLM only where reasoning is necessary

### 11.6 Frontend questions

You should be able to explain:
- component structure
- why state is split the way it is
- how loading and aborting works
- how auth restoration happens
- why some data is stored locally and some on the backend

### 11.7 Backend questions

You should be able to explain:
- route-service separation
- JWT and refresh flows
- rate limiting
- role and case checks
- asynchronous jobs
- structured errors

### 11.8 Database questions

Be ready for:
- schema design
- relationship modeling
- indexing
- transaction boundaries
- ACID properties
- why PostgreSQL over MongoDB for this data

### 11.9 API questions

Explain:
- GET vs POST
- status codes
- request validation
- pagination
- auth headers/cookies

### 11.10 Authentication/security questions

Explain:
- login vs authorization
- refresh token rotation
- bcrypt hashing
- cookie-based auth
- case isolation
- why 404 may be used instead of 403 in some private-data cases

### 11.11 Challenges faced

Good examples:
- legal queries often use language different from statutes
- law changes over time
- private case data must not leak
- simple recall is not enough
- the answer must be both accurate and readable

### 11.12 Alternative approaches

Possible alternatives:
- a pure keyword search engine
- a pure chatbot without retrieval
- a NoSQL database for app state
- a single generic workspace instead of role-based ones

Explain why those would be weaker for this problem.

### 11.13 Scalability questions

Mention:
- separation of public corpus and private case data
- async workers
- indexed retrieval
- job queueing
- pagination

### 11.14 Improvements questions

Say what you would improve next:
- readability for citizen answers
- better provision-reach bridging
- broader test coverage
- more explainable confidence labels

### 11.15 “Why did you implement it this way?”

Good answer pattern:
1. State the requirement.
2. State the risk.
3. State the tradeoff.
4. Explain why your choice was safer or simpler.

Example:
“I chose backend ownership checks because hiding a case in the UI is not enough. A user could still call the API directly, so the real boundary has to live on the server.”

---

## 12. Technical Interview Preparation

### 12.1 React questions

1. What is the difference between props and state?
2. Why use `useEffect` for data loading?
3. When would you use `useMemo`?
4. What is a controlled component?
5. How do you handle loading and error states?
6. Why use component composition?

### 12.2 JavaScript questions

1. What is the event loop?
2. What is a promise?
3. What does `async/await` do?
4. What is closure?
5. What is destructuring?
6. What is the difference between `map`, `filter`, and `reduce`?

### 12.3 Node.js questions

1. Why is Node good for I/O-heavy apps?
2. What is non-blocking I/O?
3. What is the event loop?
4. How do environment variables work?

### 12.4 Express questions

1. What is middleware?
2. How do you structure routes?
3. How do you handle errors?
4. How do you secure endpoints?

### 12.5 PostgreSQL/SQL questions

1. What is a primary key?
2. What is a foreign key?
3. What is a join?
4. Why use indexes?
5. What is normalization?
6. What is ACID?

### 12.6 MongoDB questions

1. What is a document?
2. What is a collection?
3. What is Mongoose?
4. When would you use MongoDB instead of PostgreSQL?

### 12.7 REST/API questions

1. What is REST?
2. What is idempotency?
3. What do common HTTP status codes mean?
4. What is the difference between PUT and PATCH?

### 12.8 Backend questions

1. Why separate controllers and services?
2. Why use schemas?
3. Why use async database access?
4. How do you avoid leaking private data?

### 12.9 Scenario questions

1. What happens if the database is down?
2. What happens if the vector store is unavailable?
3. What happens if the user reuses a refresh token?
4. What if the answer is incomplete?

### 12.10 Project-based questions

1. How does your legal search work?
2. Why do you have a fast lane and deep lane?
3. How do you ensure the answer is grounded?
4. How do you prevent cross-user data leakage?

### 12.11 Tricky follow-up questions

1. Why not just use one model prompt?
2. Why not trust the model if it sounds confident?
3. Why not store everything in MongoDB?
4. Why not allow admins to search all private cases?
5. Why not use only keyword search?

---

## 13. Architecture and Visual Understanding

### 13.1 Overall architecture

```text
Frontend
  -> API
    -> Auth / RBAC
    -> Services
      -> PostgreSQL
      -> Qdrant
      -> Object Storage
      -> LLM
    -> Response
  -> Frontend render
```

### 13.2 Backend architecture

```text
Router -> Service -> Model/DB or Retrieval -> Response
```

### 13.3 Database relationships

```text
User 1 --- many Cases 1 --- many Documents
User 1 --- many Chats 1 --- many Messages
User 1 --- many Audit Logs
Case 1 --- many Jobs / Generated Drafts
```

### 13.4 Authentication flow

```text
Login -> hash compare -> JWT issue -> cookie storage -> refresh -> revoke on reuse
```

### 13.5 API/request flow

```text
UI action -> fetch -> backend auth -> business logic -> database/vector search -> response -> render
```

### 13.6 Major feature flow

```text
Question -> safety screen -> retrieval -> verification -> publication -> cited answer
```

---

## 14. Final Revision

### 14.1 Most important concepts to remember

- The system is grounded in evidence.
- Private case data is isolated by ownership.
- Fast answers avoid unnecessary LLM cost.
- Deep answers are verified before publishing.
- PostgreSQL stores app state.
- Qdrant stores retrieval indexes.
- MongoDB is useful to know, but not the core database here.

### 14.2 Most likely interview questions

1. Explain your project in 1 minute.
2. Why did you choose this architecture?
3. How do you prevent hallucinations?
4. How do you handle authentication?
5. How do you stop private case leakage?
6. Why PostgreSQL instead of MongoDB?
7. What is the difference between auth and authorization?
8. How does your retrieval pipeline work?

### 14.3 Project talking points

- role-based legal research platform
- grounded answers with citations
- private case isolation
- fast vs deep retrieval lanes
- legal citation and currency handling
- admin visibility and auditability

### 14.4 Important technical definitions

- Authentication: proving identity
- Authorization: checking permissions
- RBAC: role-based access control
- ACID: transaction guarantees
- JWT: signed token for identity
- CORS: browser cross-origin security rule
- RAG: retrieval-augmented generation
- Vector search: semantic retrieval by embeddings

### 14.5 Common comparisons/differences

- React vs Angular
- PostgreSQL vs MongoDB
- Authentication vs authorization
- SQL vs NoSQL
- Fast retrieval vs deep reasoning
- UI hiding vs backend enforcement

### 14.6 Quick revision cheat sheet

If asked about the project, remember this structure:
1. Problem
2. Users
3. Architecture
4. Authentication
5. Retrieval and verification
6. Database and permissions
7. Key challenges
8. Improvements

If asked about technology choices:
1. React for UI
2. FastAPI for APIs
3. PostgreSQL for relational state
4. Qdrant for legal search
5. LLM only when deeper reasoning is needed

If asked about MongoDB:
1. Documents and collections
2. Flexible schema
3. Mongoose
4. Good for nested, changing data
5. Not the best fit for this project’s transactional app state

---

## 15. Short Interview Script

You can say this in an interview:

> I built a multi-role legal decision-support platform. A citizen, police officer, advocate, or admin can use the system, but each role gets a different workflow. The frontend is React/Next.js, the backend is FastAPI, PostgreSQL stores relational app data, and Qdrant powers legal retrieval. The system does not just generate answers; it retrieves evidence, checks claims, labels currency, protects private case data, and abstains when the corpus is not enough. That is the main design principle behind the whole project.
