# Generated by Django 3.1.5 on 2021-01-13 16:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userservice', '0002_auto_20210113_0342'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='image_url',
            field=models.CharField(default='https://tudo-media.ams3.digitaloceanspaces.com/profile-images/USER_IMAGE_tko5rq.png', max_length=400),
        ),
    ]
