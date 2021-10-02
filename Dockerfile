FROM python:3.6.9
ADD . /app
WORKDIR /app
RUN pip install pipenv && pipenv install --system --deploy --ignore-pipfile
CMD ["python", "dns-restarter.py"]
