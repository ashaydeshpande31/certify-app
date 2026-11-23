from django.db import migrations, models


def blank_means_off(apps, schema_editor):
    # in 0009 a saved blank address meant "switched off"; keep that meaning now there is a real flag
    SenderSetting = apps.get_model("certificates", "SenderSetting")
    SenderSetting.objects.filter(check_email="").update(check_disabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0009_check_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='sendersetting',
            name='check_disabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='sendersetting',
            name='recommend_chunks',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(blank_means_off, migrations.RunPython.noop),
    ]
