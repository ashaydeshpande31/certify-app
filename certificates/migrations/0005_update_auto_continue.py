from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0004_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='updatecampaign',
            name='auto_continue',
            field=models.BooleanField(
                default=False,
                help_text='Keep sending the pending people automatically when the daily Gmail limit allows.',
            ),
        ),
        migrations.AddField(
            model_name='updatecampaign',
            name='auto_status',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
