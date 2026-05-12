from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lawyers", "0006_remove_lawyerprofile_fee_band"),
    ]

    operations = [
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_model_version",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_vector",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lawyers", "0006_remove_lawyerprofile_fee_band"),
    ]

    operations = [
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_model_version",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_vector",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
