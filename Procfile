web: gunicorn wsgi:app --workers 4 --threads 2 --worker-class gthread --bind 0.0.0.0:$PORT --timeout 120 --access-logfile - --error-logfile -
