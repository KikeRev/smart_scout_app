from django.db import migrations

class Migration(migrations.RunSQL):

    DIM = 42   # ajusta

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS vector;"),
        migrations.RunSQL(f"""
            ALTER TABLE players
            ADD COLUMN IF NOT EXISTS feature_emb vector({DIM});
            UPDATE players
            SET feature_emb = feature_vector::vector
            WHERE feature_emb IS NULL;
            ALTER TABLE players
            DROP COLUMN IF EXISTS feature_vector;
            ALTER TABLE players
            RENAME COLUMN feature_emb TO feature_vector;
        """),
        migrations.RunSQL("""
            CREATE INDEX IF NOT EXISTS players_feature_vec_idx
            ON players USING ivfflat (feature_vector vector_cosine_ops)
            WITH (lists = 100);
        """),
    ]
