from django.db import migrations
from pgvector.django import HnswIndex, VectorField


class Migration(migrations.Migration):
    dependencies = [
        ("lawyers", "0007_lawyerprofile_embedding_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector",
        ),
        migrations.AddField(
            model_name="lawyerprofile",
            name="embedding_vector_v2",
            field=VectorField(blank=True, dimensions=384, null=True),
        ),
        migrations.AddIndex(
            model_name="lawyerprofile",
            index=HnswIndex(
                fields=["embedding_vector_v2"],
                name="lawyer_emb_v2_hnsw",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
