import json

import flask
from zeeguu.api.endpoints.feature_toggles import features_for_user
import zeeguu.core
from zeeguu.core.model import User

from zeeguu.api.utils.json_result import json_result
from zeeguu.api.utils.route_wrappers import cross_domain, requires_session
from . import api
from ...core.model import UserPreference, UserActivityData, UserArticle, Article


@api.route("/learned_language", methods=["GET"])
@cross_domain
@requires_session
def learned_language():
    """
    Each endpoint is defined by a function definition
    of the same form as this one.

    The important information for understanding the
    endpoint is in the annotations before the function
    and in the comment immediately after the function
    name.

    Two types of annotations are important:

     @endpoints.route gives you the endpoint name together
        with the expectd HTTP method
        it is normally appended to the API_URL (https://www.zeeguu.unibe.ch/)

     @with_session means that you must submit a session
        argument together wit your API request
        e.g. API_URL/learned_language?session=123141516
    """
    user = User.find_by_id(flask.g.user_id)
    return user.learned_language.code


@api.route("/learned_language/<language_code>", methods=["POST"])
@cross_domain
@requires_session
def learned_language_set(language_code):
    """
    Set the learned language
    :param language_code: one of the ISO language codes
    :return: "OK" for success
    """
    user = User.find_by_id(flask.g.user_id)
    user.set_learned_language(language_code, session=zeeguu.core.model.db.session)
    zeeguu.core.model.db.session.commit()
    return "OK"


@api.route("/native_language", methods=["GET"])
@cross_domain
@requires_session
def native_language():
    user = User.find_by_id(flask.g.user_id)
    return user.native_language.code


@api.route("/native_language/<language_code>", methods=["POST"])
@cross_domain
@requires_session
def native_language_set(language_code):
    """
    :param language_code:
    :return: OK for success
    """
    user = User.find_by_id(flask.g.user_id)
    user.set_native_language(language_code)
    zeeguu.core.model.db.session.commit()
    return "OK"


@api.route("/learned_and_native_language", methods=["GET"])
@cross_domain
@requires_session
def learned_and_native_language():
    """
    Get both the native and the learned language
    for the user in session
    :return:
    """
    user = User.find_by_id(flask.g.user_id)
    res = dict(native=user.native_language_id, learned=user.learned_language_id)
    return json_result(res)

@api.route("/get_user_unfinished_reading_sessions", methods=("GET",))
@cross_domain
@requires_session
def get_user_unfinished_reading_sessions():
    """
        Retrieves the last uncompleted sessions based on the SCROLL events of the user.

    """
    user = User.find_by_id(flask.g.user_id)
    last_sessions = UserActivityData.get_scroll_events_for_user_in_date_range(user)
    list_result = []
    for s in last_sessions:
        art_id, date_str, viewport_settings, last_reading_point = s
        if last_reading_point < 100 and last_reading_point > 0:
            scrollHeight = viewport_settings["scrollHeight"]
            clientHeight = viewport_settings["clientHeight"]
            bottomRowHeight = viewport_settings["bottomRowHeight"]
            art = Article.find_by_id(art_id)
            art_info = UserArticle.user_article_info(user, art)
            art_info["pixel_to_scroll_to"] = (scrollHeight - clientHeight - bottomRowHeight) * (last_reading_point)
            art_info["time_until_last_read"] = date_str
            art_info["last_reading_percentage"] = last_reading_point
            list_result.append(art_info)
        if len(list_result) >= 1:
            break

    return json_result(list_result)

@api.route("/get_user_details", methods=("GET",))
@cross_domain
@requires_session
def get_user_details():
    """
    after the login, this information might be useful to be displayed
    by an app
    :param lang_code:
    :return:
    """
    user = User.find_by_id(flask.g.user_id)
    details_dict = user.details_as_dictionary()
    details_dict["features"] = features_for_user(user)

    return json_result(details_dict)


@api.route("/user_settings", methods=["POST"])
@cross_domain
@requires_session
def user_settings():
    """
    set the native language of the user in session
    :return: OK for success
    """

    data = flask.request.form
    user = User.find_by_id(flask.g.user_id)

    submitted_name = data.get("name", None)
    if submitted_name:
        user.name = submitted_name

    submitted_native_language_code = data.get("native_language", None)
    if submitted_native_language_code:
        user.set_native_language(submitted_native_language_code)

    cefr_level = data.get("cefr_level", None)
    if cefr_level is None:
        return "ERROR"

    submitted_learned_language_code = data.get("learned_language", None)
    if submitted_learned_language_code:
        user.set_learned_language(
            submitted_learned_language_code, cefr_level, zeeguu.core.model.db.session
        )

    submitted_email = data.get("email", None)
    if submitted_email:
        user.email = submitted_email

    zeeguu.core.model.db.session.add(user)
    zeeguu.core.model.db.session.commit()
    return "OK"


@api.route("/send_feedback", methods=["POST"])
@cross_domain
@requires_session
def send_feedback():

    message = flask.request.form.get("message", "")
    context = flask.request.form.get("context", "")
    print(message)
    print(context)
    from zeeguu.core.emailer.zeeguu_mailer import ZeeguuMailer

    user = User.find_by_id(flask.g.user_id)
    ZeeguuMailer.send_feedback("Feedback", context, message, user)
    return "OK"
