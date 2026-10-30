# G.N.A.ID Python Store

A Flask-based e-commerce platform for the G.N.A.ID online store with full product management, payment processing, shipping integration, and discount system.

# Features

- **Product Management**: Products with variants (colors, sizes), images, videos, and Shopee affiliate links
- **Discount System**: Product discounts (percentage/fixed) and shipping discounts with snapshot integrity
- **Payment Integration**: Xendit payment gateway with invoice handling
- **Shipping Integration**: Biteship API for real-time shipping rates and tracking
- **Order Management**: Order lifecycle management with auto-cancelation for expired payments
- **User Authentication**: Admin/employee roles with secure password reset via OTP email
- **Rate Limiting**: Configurable rate limiting with Redis support for production
- **Monitoring**: Sentry integration for error tracking and performance monitoring
- **TikTok Pixel**: Optional TikTok Pixel tracking for analytics
- **Maintenance Mode**: Toggle maintenance mode with custom messages
- **Audit Logging**: Complete audit trail for admin actions

# Technology Stack

- **Backend**: Flask 3.0+, Flask-SQLAlchemy, Flask-Migrate
- **Database**: MySQL with PyMySQL driver
- **Payment**: Xendit Python SDK
- **Shipping**: Biteship API
- **Rate Limiting**: Flask-Limiter with Redis support
- **Monitoring**: Sentry SDK
- **Security**: bcrypt for password hashing, CSRF protection, session management
- **Deployment**: Gunicorn WSGI server

# About This Project

This e-commerce platform was developed as a freelance project for G.N.A.ID, featuring a complete online store solution with payment integration, shipping management, and discount systems.

# Developed By

**Freelance Developer**
- Full-stack Flask development
- Payment gateway integration (Xendit)
- Shipping API integration (Biteship)
- Custom discount and order management systems
- Security implementation (CSRF, rate limiting, OTP authentication)
