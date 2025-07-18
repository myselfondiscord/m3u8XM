# Use Alpine Linux as base image
FROM alpine:latest

# Install Python 3 and requests
RUN apk add --no-cache python3 py3-requests

# Set working directory
WORKDIR /app

# Copy the Python script and config files
COPY sxm.py /app/

# Expose the default port (8888)
EXPOSE 8888

# Run the application
CMD ["python3", "sxm.py"]
