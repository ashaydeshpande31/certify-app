from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0007_external_usage'),
    ]

    operations = [
        migrations.AddField(model_name='event', name='extra_data', field=models.BinaryField(blank=True, null=True)),
        migrations.AddField(model_name='event', name='extra_name', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='event', name='extra_type', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='student', name='send_extra', field=models.BooleanField(default=False, help_text="Also attach the event's extra file to this person's email.")),
    ]
