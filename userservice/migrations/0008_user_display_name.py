# Generated by Django 3.1.5 on 2021-02-19 13:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userservice', '0007_user_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='display_name',
            field=models.CharField(default=None, max_length=100, null=True),
        ),
    ]
