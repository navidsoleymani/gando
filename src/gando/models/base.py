from gando.middlewares.global_state import CurrentRequestMiddleware


def global_request():
    return CurrentRequestMiddleware.get_request()


def current_user_id():
    try:
        return global_request().user.id
    except:
        return None


def current_user_agent_info():
    try:
        return global_request().uad.to_dict()

    except:
        return {}









