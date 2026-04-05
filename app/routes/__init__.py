def register_routes(app):
    from app.routes.urls import urls_bp
    from app.routes.metrics import metrics_bp
    from app.routes.users import users_bp
    app.register_blueprint(urls_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(users_bp)
