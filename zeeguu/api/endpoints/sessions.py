import flask
from datetime import datetime
from flask import request, make_response
from zeeguu.core.model import Session, User
from zeeguu.api.utils.abort_handling import make_error

from zeeguu.api.utils.route_wrappers import cross_domain, has_session
from . import api, db_session

MAX_TIME_SESSION = 30  # Days


def validate_session(session_object):
    print("----------- Validating the Session based on Last use!! -----------")
    if session_object is None:
        flask.abort(401)
    is_session_too_old = (
        datetime.now() - session_object.last_use
    ).days > MAX_TIME_SESSION
    if is_session_too_old:
        print("Session was too old! - logging out!")
        db_session.delete(session_object)
        db_session.commit()
        flask.abort(401)
        return False
    return True


@api.route("/session/<email>", methods=["POST"])
@cross_domain
def get_session(email):
    """
    If the email and password match,
    a sessionId is returned as a string.
    This sessionId can to be passed
    along all the other requests that are annotated
    with @with_user in this file
    """

    password = request.form.get("password", None)
    if password == "":
        return make_error(401, "Password not given")

    if not User.email_exists(email):
        return make_error(401, "There is no account associated with this email")

    user = User.authorize(email, password)
    if user is None:
        return make_error(401, "Invalid credentials")
    session = Session.create_for_user(user)
    db_session.add(session)
    db_session.commit()
    resp = make_response({"session": session.uuid})
    resp.set_cookie("chocolatechip", str(session.uuid))
    return resp


@api.route("/get_anon_session/<uuid>", methods=["POST"])
@cross_domain
def get_anon_session(uuid):
    """

    If the uuid and password match, a  sessionId is
    returned as a string. This sessionId can to be passed
    along all the other requests that are annotated
    with @with_user in this file

    """
    password = request.form.get("password", None)

    if password is None:
        flask.abort(400)
    user = User.authorize_anonymous(uuid, password)
    if user is None:
        flask.abort(401)
    session = Session.create_for_user(user)
    db_session.add(session)
    db_session.commit()
    return str(session.id)


@api.route("/validate")
@cross_domain
@has_session
def validate():
    """

        If your session is valid, you will get an OK.
        Use this one to test that you are holding a
        valid session.

    :return:
    """
    # TODO: ideally update in parallel with running the decorated method?
    session_object = Session.find(flask.g.session_uuid)
    validate_session(session_object)
    session_object.update_use_date()
    db_session.add(session_object)
    db_session.commit()
    return "OK"


@cross_domain
@api.route("/is_up")
def is_up():
    """

        Useful for testing that the server is up

    :return:
    """
    return "OK"


@api.route("/logout_session", methods=["GET"])
@cross_domain
@has_session
def logout():
    """

    Deactivate a given session.

    """

    try:
        session_uuid = request.args["session"]
        session = Session.find(session_uuid)
        db_session.delete(session)
        db_session.commit()
    except:
        flask.abort(401)

    return "OK"
