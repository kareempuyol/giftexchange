from flask import jsonify


def ok(data=None, message="ok", status=200):
    return jsonify({"code": 0, "data": data, "message": message}), status


def fail(message, status=400, code=-1, headers=None):
    resp = jsonify({"code": code, "data": None, "message": message})
    if headers:
        for k, v in headers.items():
            resp.headers[k] = v
    return resp, status
