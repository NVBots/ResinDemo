import os
from flask import Flask
app = Flask(__name__)

MESSAGE = 'Hello Docker Boston!'
if 'MESSAGE' in os.environ:
    MESSAGE = os.environ['MESSAGE']

@app.route("/")
def hello():
    return MESSAGE

if __name__ == "__main__":
    app.run(debug=True)
