from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0011_deleted_entry'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='font_choice',
            field=models.CharField(default='serif', max_length=40),
        ),
    ]
