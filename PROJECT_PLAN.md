Enterprise CRM System
Complete Project Plan & Technical Specification

Version: 1.0

1. Project Overview

Develop an enterprise-grade Customer Relationship Management (CRM) platform that enables organizations to efficiently manage customers, leads, sales pipelines, communications, projects, documents, tasks, reports, and business automation.

The application should be modular, scalable, secure, AI-ready, and optimized for deployment on a VPS.

2. Objectives

The CRM should help organizations:

Manage Customers
Manage Companies
Track Leads
Manage Sales Pipeline
Manage Quotations
Schedule Meetings
Track Calls
Manage Tasks
Maintain Activity History
Generate Reports
Send Emails
Manage Documents
Handle Projects
Assign Work
Provide Dashboards
Support Automation
Support AI features in future releases

3. Technology Stack
Frontend
React.js
TypeScript
Tailwind CSS
React Router
Axios
React Hook Form
Zod
TanStack Query
Recharts
Socket.IO Client

Backend
Python
FastAPI
SQLAlchemy 2.0
Alembic
Pydantic
Celery
Redis


Database
PostgreSQL

Extensions
pgvector
uuid-ossp
pg_trgm
unaccent


Search Engine
Meilisearch

File Storage
MinIO

Authentication
JWT Authentication
Access Token
Refresh Token

Email
SMTP
Supports,
Password Reset
Welcome Email
Lead Notifications
Workflow Emails
Quotations

Real Time Notifications
Socket.IO
Examples,
Lead Assigned
Deal Updated
Mention User
Task Assigned
Meeting Reminder

Charts
Recharts

Reverse Proxy
Nginx

SSL
Let's Encrypt

Deployment
Docker Compose

Hosted on
VPS

4. Application Architecture

Use a Modular Monolith Architecture.

Every module should have its own:

API
Services
Schemas
Models
Repository
Business Logic

Each module should remain independent while sharing common infrastructure.

React Frontend

        │

 REST APIs

        │

FastAPI Backend

        │

──────────────────────────────

Authentication

Users

CRM

Projects

Tasks

Reports

Automation

Notifications

Settings

──────────────────────────────

        │

 PostgreSQL

        │

Redis

Meilisearch

MinIO

SMTP

Socket.IO


5. Folder Structure

crm/

frontend/

    src/

        assets/

        components/

        pages/

        layouts/

        hooks/

        context/

        routes/

        services/

        types/

        utils/

        styles/

backend/

    app/

        core/

        auth/

        users/

        companies/

        contacts/

        leads/

        deals/

        pipeline/

        activities/

        tasks/

        meetings/

        calendar/

        products/

        quotations/

        invoices/

        projects/

        support/

        reports/

        notifications/

        automation/

        search/

        storage/

        settings/

        websocket/

        utils/

        middleware/

        database/

        schemas/

        services/

        models/

        repositories/

    migrations/

docker/

nginx/

docs/

scripts/

6. User Roles
Super Admin
Admin
Sales Manager
Sales Executive
Marketing
Support
Finance
HR
Viewer
Custom role

Role Based Access Control (RBAC) should be implemented throughout the application.

7. Core Modules

>Dashboard
KPI Cards
Revenue
Active Leads
Open Deals
Won Deals
Tasks Due Today
Upcoming Meetings
Activity Timeline
Monthly Sales
Team Performance

>Companies
Company Details
Industry
Address
Website
GST
Assigned Manager
Notes
Documents

>Contacts
Contact Information
Multiple Emails
Multiple Phone Numbers
Position
Associated Company
Social Links
Notes
Tags

>Leads
Lead Source
Status
Score
Assigned User
Notes
Activities
Attachments
Follow-up Schedule

>Deals
Deal Value
Probability
Expected Closing
Assigned Salesperson
Pipeline Stage
Competitors
Notes

>Sales Pipeline
Stages:
New
Contacted
Qualified
Proposal
Negotiation
Won
Lost
Supports Drag & Drop Kanban.

>Tasks
Priority
Due Date
Assigned User
Status
Comments
Attachments

>Calendar
Meetings
Calls
Follow-ups
Reminders

>Meetings
Agenda
Participants
Notes
Follow-up Tasks

>Activities
Track:
Emails
Calls
Meetings
Notes
Status Changes
Assignments

Complete audit history.


>Products
SKU
Pricing
Category
Tax
Stock (Optional)

>Quotations
Generate Quote
PDF Export
Email Quote
Convert to Invoice

>Invoices
Invoice Number
Taxes
Payment Status

>Documents
Store:
PDFs
Images
Contracts
Attachments

Stored in MinIO.


>Projects
Customer Projects
Milestones
Assigned Team
Timeline
Files

>Support Tickets
Ticket Number
Customer
Priority
Status
Resolution

>Reports
Revenue
Sales Funnel
Win Rate
Lead Sources
Team Performance
Customer Growth
Conversion Rate
Activity Reports

>Notifications
Real-time notifications using Socket.IO.

>Search
Global search powered by Meilisearch.
Search:
Leads
Companies
Contacts
Deals
Tasks
Projects

>Settings
Company Profile
SMTP
Users
Roles
Branding
Notification Settings
Email Templates


Try to have the common things together as a separate modules and make sure we have less number of modules which keeps user friendly.

8. Database Design

Main Tables:

users

roles

permissions

companies

contacts

leads

lead_sources

deal_stages

deals

activities

tasks

meetings

calendar_events

products

quotations

quotation_items

invoices

invoice_items

projects

project_tasks

documents

tickets

notifications

settings

email_templates

audit_logs

tags

comments

attachments


9. Background Jobs

Use Celery + Redis.

Jobs:

Send Emails
Lead Assignment
Reminder Notifications
Daily Reports
Weekly Reports
Search Index Updates
File Processing
PDF Generation
Scheduled Tasks


10. Security

JWT Authentication
Refresh Tokens
Password Hashing (bcrypt)
Rate Limiting
Input Validation
SQL Injection Protection
CORS
CSRF Protection (where applicable)
Audit Logging

11. API Design

REST API

/api/v1/auth

/api/v1/users

/api/v1/companies

/api/v1/contacts

/api/v1/leads

/api/v1/deals

/api/v1/tasks

/api/v1/projects

/api/v1/products

/api/v1/reports

/api/v1/settings


Use consistent JSON responses.


12. UI/UX Design Guidelines
Design Language:

The application should have a modern SaaS-style interface inspired by platforms such as HubSpot, Salesforce Lightning, Monday.com, Linear, and Notion. The design should prioritize clarity, speed, and ease of use.

Design Principles:
Clean and minimal interface
Consistent spacing using an 8px grid
High readability with clear typography
Responsive layout for desktop and tablet
Fast navigation with minimal clicks
Accessibility-focused (WCAG compliant where possible)

Color Palette:
Primary: Indigo (#4F46E5)
Secondary: Slate (#64748B)
Success: Emerald (#10B981)
Warning: Amber (#F59E0B)
Danger: Red (#EF4444)
Background: Light Gray (#F8FAFC)
Surface: White (#FFFFFF)
Text: Slate Gray (#1E293B)

Typography:
Font Family: Inter
Headings: Semi-bold
Body: Regular
Clear visual hierarchy

Layout Structure:
Collapsible left navigation sidebar
Sticky top header with global search
Right-side notification panel
Breadcrumb navigation
Responsive content area
Dashboard widgets with card-based layout

Navigation Sidebar Modules:

Dashboard
Companies
Contacts
Leads
Deals
Pipeline
Calendar
Tasks
Projects
Products
Quotations
Invoices
Support
Reports
Settings


Dashboard Experience
Dashboard should include:

KPI summary cards
Sales pipeline overview
Monthly revenue chart
Lead conversion chart
Upcoming meetings
Tasks due today
Recent activities
Top-performing sales representatives


Forms:
Multi-column layouts
Inline validation
Auto-save drafts where appropriate
Reusable form components
Stepper UI for complex workflows

Tables:
Sticky headers
Server-side pagination
Column sorting
Advanced filtering
Bulk actions
Column visibility controls
CSV/Excel export

Kanban Boards:
Drag-and-drop deal stages
Visual stage indicators
Quick-edit cards
Deal value badges
Assignee avatars

Responsive Design:
Desktop-first with tablet optimization
Adaptive sidebar
Responsive tables with horizontal scrolling
Mobile-friendly forms for future extension

Micro-interactions:
Smooth transitions (200–300 ms)
Loading skeletons
Toast notifications
Confirmation dialogs
Empty-state illustrations
Contextual tooltips

Theme Support:
Light Mode
Dark Mode
Theme preference saved per user

13. Deployment Architecture

Internet

      │

Nginx (Reverse Proxy)

      │

──────────────────────────────

React Frontend

FastAPI Backend

Celery Worker

Celery Beat

Redis

PostgreSQL

Meilisearch

MinIO

──────────────────────────────

Docker Compose

      │

Contabo VPS


15. Development Standards
Strict TypeScript on the frontend
Python type hints throughout the backend
Modular code organization
Repository and service layer pattern
RESTful API conventions
Comprehensive logging
Automated testing (unit and integration)
API documentation with FastAPI's OpenAPI/Swagger
Environment-based configuration
Dockerized development and production environments
Git-based version control with feature branching

This document serves as the single source of truth for the CRM project and provides Claude Code with a clear, structured blueprint for building a production-ready, enterprise-grade CRM application.

