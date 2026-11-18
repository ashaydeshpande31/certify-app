from django.urls import path
from . import views, update_views

urlpatterns = [
    path("", views.home, name="home"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms_of_service, name="terms_of_service"),
    path("create/", views.create_event, name="create_event"),
    path("event/<int:event_id>/position/", views.position_certificate, name="position_certificate"),
    path('event/<int:event_id>/delete/', views.delete_event, name='delete_event'),
    path("event/<int:event_id>/students/", views.student_list, name="student_list"),
    path("event/<int:event_id>/message/", views.update_message, name="update_message"),
    path("event/<int:event_id>/students/quick-add/", views.add_quick_send_student, name="add_quick_send_student"),
    path("event/<int:event_id>/students/<int:student_id>/edit/", views.update_student, name="update_student"),
    path("event/<int:event_id>/generate/", views.generate_all, name="generate_all"),
    path("event/<int:event_id>/send/", views.send_all, name="send_all"),
    path("event/<int:event_id>/send/<int:student_id>/", views.send_one, name="send_one"),
    path("verify/<uuid:cert_id>/", views.verify_certificate, name="verify_certificate"),

    # "Send Updates" section (announcement emails, no certificate)
    path("updates/new/", update_views.update_create, name="update_create"),
    path("updates/<int:campaign_id>/", update_views.update_detail, name="update_detail"),
    path("updates/<int:campaign_id>/edit/", update_views.update_edit, name="update_edit"),
    path("updates/<int:campaign_id>/add/", update_views.update_add_recipient, name="update_add_recipient"),
    path("updates/<int:campaign_id>/send-batch/", update_views.update_send_batch, name="update_send_batch"),
    path("updates/<int:campaign_id>/reset-failed/", update_views.update_reset_failed, name="update_reset_failed"),
    path("updates/<int:campaign_id>/delete/", update_views.update_delete, name="update_delete"),
    path("updates/<int:campaign_id>/auto/", update_views.update_toggle_auto, name="update_toggle_auto"),
    path("quota/", update_views.quota_status, name="quota_status"),
    path("delivery/search/", update_views.delivery_search, name="delivery_search"),
    path("cron/continue/", update_views.cron_continue, name="cron_continue"),
]
