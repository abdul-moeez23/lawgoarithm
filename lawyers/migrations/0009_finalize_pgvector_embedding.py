from django.db import migrations
from pgvector.django import HnswIndex


class Migration(migrations.Migration):
    dependencies = [
        ("lawyers", "0008_pgvector_embedding_v2"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="lawyerprofile",
            name="embedding_vector",
        ),
        migrations.RenameField(
            model_name="lawyerprofile",
            old_name="embedding_vector_v2",
            new_name="embedding_vector",
        ),
        migrations.RemoveIndex(
            model_name="lawyerprofile",
            name="lawyer_emb_v2_hnsw",
        ),
        migrations.AddIndex(
            model_name="lawyerprofile",
            index=HnswIndex(
                fields=["embedding_vector"],
                name="lawyer_emb_hnsw",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
