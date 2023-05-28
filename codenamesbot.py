from itertools import combinations
from random import sample
import psycopg2

def load_codenames_words():
    with open('data/codenames_words.txt', 'r') as f:
        codenames_words = [word.strip().lower() for word in f.readlines()]
    
    codenames_words.remove('ice cream')
    codenames_words.remove('loch ness')
    codenames_words.remove('new york')
    codenames_words.remove('scuba diver')

    return codenames_words

class CodenamesClueGiver:
    def __init__(self, database_uri):
        self.code_words = load_codenames_words()

        try:
            self.conn = psycopg2.connect(database_uri)
        except:
            print("I am unable to connect to the database")

        self.pmi_table_name = 'pmi_v0_3'
    
    def __del__(self):
        self.conn.close()

    def generate_best_clue(self, game_id, table_words, target_words, trap_words, previous_clues=None):

        clue = None

        if len(target_words) == 1:
            curr_target_words = target_words
            
            clue_1, score_1, _ = self.get_best_single_word_clue(game_id, table_words, curr_target_words[0], trap_words, previous_clues)

            clue = clue_1
            score = score_1
            best_target_words = target_words
            
        if len(target_words) >= 2:
            best_score_2 = -10000
            for curr_target_words in combinations(target_words, 2):
                clue_2, score_2, _ = self.generate_clue_for_specific_target_words(game_id, table_words, curr_target_words, trap_words, previous_clues)
                if clue_2 is not None and score_2 > best_score_2:
                    best_score_2 = score_2
                    best_clue_2 = clue_2
                    best_target_words_2 = curr_target_words

            clue = best_clue_2
            score = best_score_2
            best_target_words = best_target_words_2

        if len(target_words) >= 3:
            best_score_3 = -10000
            combos_3 = list(combinations(target_words, 3))
            if len(combos_3) > 20:
                combos_3 = sample(combos_3, 20)
            for curr_target_words in combos_3:
                clue_3, score_3, _ = self.generate_clue_for_specific_target_words(game_id, table_words, curr_target_words, trap_words, previous_clues)
                if clue_3 is not None and score_3 > best_score_3:
                    best_score_3 = score_3
                    best_clue_3 = clue_3
                    best_target_words_3 = curr_target_words

            if best_score_3 > 0.8 * best_score_2:
                clue = best_clue_3
                score = best_score_3
                best_target_words = best_target_words_3

        return clue, score, best_target_words


    def generate_clue_for_specific_target_words(self, game_id, table_words, target_words, trap_words, previous_clues = None):
        clues = self.query_database(game_id, table_words, target_words, trap_words, previous_clues)


        if len(clues) == 0:
            return None, -10000, None
        else:
            clue = clues[0][0]
            score_diff = clues[0][9]

            return clue, score_diff, clues
        
    def create_temp_table(self, game_id, table_words):

        like_conditions = ""
        for table_word in table_words:
            like_condition = f"\n AND word2 != '{table_word}' AND word2 NOT LIKE '%{table_word}%' AND '{table_word}' NOT LIKE CONCAT('%', word2, '%') "
            like_conditions += like_condition
                
        # Open a cursor to perform database operations
        cur = self.conn.cursor()

        # Execute the SQL query with the word list as a parameter
        temp_table_query = f"""
            CREATE TEMPORARY TABLE IF NOT EXISTS temp_${game_id} AS (
                SELECT * FROM pmi_v0_3 WHERE word1 in {tuple(table_words)}
                {like_conditions}
            );
        """
        # print(temp_table_query)
        cur.execute(temp_table_query)
    
    def get_best_single_word_clue(self, game_id, table_words, target_word, trap_words, previous_clues = None):

        cur = self.conn.cursor()

        self.create_temp_table(game_id, table_words)

        if previous_clues:
            placeholders = ', '.join(f"'{clue}'" for clue in previous_clues)
            previous_clues_param = 'WHERE word2 NOT IN (%s)' % placeholders
        else:
            previous_clues_param = ''

        query = f"""
            WITH t1 AS (
                SELECT
                    word2,
                    word1 in %s as is_target,
                    max(COALESCE(pmi, 0)) as max_pmi,
                    min(COALESCE(pmi, 0)) as min_pmi,
                    min(COALESCE(joint_value, 0)) as min_joint_value,
                    max(COALESCE(joint_value, 0)) as max_joint_value
                FROM temp_${game_id}
                {previous_clues_param}
                GROUP BY
                    word2, is_target
            ), t2 AS (
                SELECT
                    word2,
                    COALESCE(MAX(CASE WHEN is_target = TRUE THEN min_pmi ELSE null END), 0) AS min_pmi_target,
                    COALESCE(MAX(CASE WHEN is_target = TRUE THEN max_pmi ELSE null END), 0) AS max_pmi_target,
                    COALESCE(MAX(CASE WHEN is_target = FALSE THEN min_pmi ELSE null END), 0) AS min_pmi_non,
                    COALESCE(MAX(CASE WHEN is_target = FALSE THEN max_pmi ELSE null END), 0) AS max_pmi_non,
                    COALESCE(MAX(CASE WHEN is_target = TRUE THEN min_joint_value ELSE null END), 0) AS min_jv_target,
                    COALESCE(MAX(CASE WHEN is_target = TRUE THEN max_joint_value ELSE null END), 0) AS max_jv_target,
                    COALESCE(MAX(CASE WHEN is_target = FALSE THEN min_joint_value ELSE null END), 0) AS min_jv_non,
                    COALESCE(MAX(CASE WHEN is_target = FALSE THEN max_joint_value ELSE null END), 0) AS max_jv_non
                FROM t1
                GROUP BY word2
            )
            SELECT
                *,
                min_pmi_target - 0.1 * max_pmi_non AS pmi_diff 
            FROM
                t2
            WHERE 
                min_jv_target > 2 * max_jv_non
            ORDER BY
                min_jv_target DESC
            LIMIT 1;
        """

        cur.execute(query, ((target_word,), ))

        rows = cur.fetchall()

        clue = rows[0][0]
        score_diff = rows[0][-1]

        return clue, score_diff, rows
        
    def query_database(self, game_id, table_words, target_words, trap_words, previous_clues = None):
        # print('querying database...')

        if previous_clues:
            placeholders = ', '.join(f"'{clue}'" for clue in previous_clues)
            previous_clues_param = 'WHERE word2 NOT IN (%s)' % placeholders
        else:
            previous_clues_param = ''

        try:
            self.create_temp_table(game_id, table_words)

            cur = self.conn.cursor()

            query = f"""
                WITH t1 AS (
                    SELECT
                        word2,
                        word1 in %s as is_target,
                        max(COALESCE(pmi, 0)) as max_pmi,
                        min(COALESCE(pmi, 0)) as min_pmi,
                        min(COALESCE(joint_value, 0)) as min_joint_value,
                        max(COALESCE(joint_value, 0)) as max_joint_value
                    FROM temp_${game_id}
                        {previous_clues_param}
                    GROUP BY
                        word2, is_target
                ), t2 AS (
                    SELECT
                        word2,
                        COALESCE(MAX(CASE WHEN is_target = TRUE THEN min_pmi ELSE null END), 0) AS min_pmi_target,
                        COALESCE(MAX(CASE WHEN is_target = TRUE THEN max_pmi ELSE null END), 0) AS max_pmi_target,
                        COALESCE(MAX(CASE WHEN is_target = FALSE THEN min_pmi ELSE null END), 0) AS min_pmi_non,
                        COALESCE(MAX(CASE WHEN is_target = FALSE THEN max_pmi ELSE null END), 0) AS max_pmi_non,
                        COALESCE(MAX(CASE WHEN is_target = TRUE THEN min_joint_value ELSE null END), 0) AS min_jv_target,
                        COALESCE(MAX(CASE WHEN is_target = TRUE THEN max_joint_value ELSE null END), 0) AS max_jv_target,
                        COALESCE(MAX(CASE WHEN is_target = FALSE THEN min_joint_value ELSE null END), 0) AS min_jv_non,
                        COALESCE(MAX(CASE WHEN is_target = FALSE THEN max_joint_value ELSE null END), 0) AS max_jv_non
                    FROM t1
                    GROUP BY word2
                )
                SELECT
                    *,
                    min_pmi_target - 0.8 * max_pmi_non AS pmi_diff 
                FROM
                    t2
                WHERE 
                    min_jv_target > 10
                ORDER BY
                    pmi_diff DESC
                LIMIT 10;
            """
        
            cur.execute(query, (tuple(target_words), ))

            # Fetch all rows and print them
            rows = cur.fetchall()

            # for row in rows:
                # print(row)
            
            return rows

        except Exception as e:
            print("Error executing SQL query: ", e)
