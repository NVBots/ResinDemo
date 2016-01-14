import os
from flask import Flask
app = Flask(__name__)

MESSAGE = 'Hello World!'
if 'MESSAGE' in os.environ:
    MESSAGE = os.environ['MESSAGE']

@app.route("/")
def hello():
    return MESSAGE

if __name__ == "__main__":
    app.run('0.0.0.0', port=80)
