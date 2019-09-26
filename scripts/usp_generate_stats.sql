CREATE PROCEDURE `generate_stats`()
BEGIN
    DROP TEMPORARY TABLE IF EXISTS PIVOT_1;
    CREATE TEMPORARY TABLE PIVOT_1
    SELECT CR.ID,
           TYPE,
           MAX(
                   CASE WHEN PARTICIPANT_NUMBER = "1" THEN BOT_ID END
               ) "BOT1",
           MAX(
                   CASE WHEN PARTICIPANT_NUMBER = "2" THEN BOT_ID END
               ) "BOT2"
    FROM core_result CR
             INNER JOIN core_participation CM ON CR.MATCH_ID = CM.MATCH_ID
    GROUP BY ID,
             TYPE;
    DROP TEMPORARY TABLE IF EXISTS PIVOT_2;
    CREATE TEMPORARY TABLE PIVOT_2 LIKE PIVOT_1;
    INSERT INTO PIVOT_2
    SELECT *
    FROM PIVOT_1;
    CREATE UNIQUE INDEX IDX_PIVOT1_ID ON PIVOT_1 (ID);CREATE UNIQUE INDEX IDX_PIVOT2_ID ON PIVOT_2 (ID);
    DROP TEMPORARY TABLE IF EXISTS STEP1_1;
    CREATE TEMPORARY TABLE STEP1_1
    SELECT CASE WHEN K.BOT1 < K.BOT2 THEN K.BOT2 ELSE K.BOT1 END AS BOT1,
           CASE WHEN K.BOT1 > K.BOT2 THEN K.BOT2 ELSE K.BOT1 END AS BOT2,
           SUM(
                   CASE WHEN WINNER_ID = (CASE WHEN BOT1 < BOT2 THEN BOT2 ELSE BOT1 END) THEN 1 ELSE 0 END
               )                                                 AS WINS,
           SUM(
                   CASE WHEN WINNER_ID != (CASE WHEN BOT1 < BOT2 THEN BOT2 ELSE BOT1 END) THEN 1 ELSE 0 END
               )                                                 AS LOSSES
    FROM core_result CR
             LEFT JOIN PIVOT_1 K ON CR.ID = K.ID -- WHERE (K.BOT1 = 32 OR K.BOT2=32) AND (K.BOT1 = 30 OR K.BOT2=30)
    GROUP BY BOT1,
             BOT2;
    DROP TEMPORARY TABLE IF EXISTS STEP1_2;
    CREATE TEMPORARY TABLE STEP1_2 LIKE STEP1_1;
    INSERT INTO STEP1_2
    SELECT *
    FROM STEP1_1;
    DROP TEMPORARY TABLE IF EXISTS STATS_BOT_PERC;
    CREATE TEMPORARY TABLE STATS_BOT_PERC
    SELECT DISTINCT BOT1                                              AS BOT_ID,
                    BOT2                                              AS OPPONENT_ID,
                    SUM(COALESCE(WINS, 0))                            AS WINS,
                    SUM(COALESCE(WINS, 0)) + SUM(COALESCE(LOSSES, 0)) AS TOTAL_GAMES,
                    COALESCE(
                            (
                                        SUM(COALESCE(WINS, 0)) / (SUM(COALESCE(WINS, 0)) + SUM(COALESCE(LOSSES, 0))) *
                                        100
                                ),
                            0.00
                        )                                             AS WIN_PERC,
                    0                                                 AS CRASHES,
                    000.00                                            AS OVERALL_WIN_PERC,
                    000.00                                            AS OVERALL_CRASH_PERC,
                    CONVERT_TZ(NOW(), @@SESSION.TIME_ZONE, '+00:00')  AS GENERATED_AT
    FROM STEP1_1
    GROUP BY BOT1,
             BOT2
    UNION
    SELECT DISTINCT BOT2                                                                                 AS BOT_ID,
                    BOT1                                                                                 AS OPPONENT_ID,
                    SUM(COALESCE(LOSSES, 0))                                                             AS WINS,
                    SUM(COALESCE(WINS, 0)) + SUM(COALESCE(LOSSES, 0))                                    AS TOTAL_GAMES,
                    SUM(COALESCE(LOSSES, 0)) / (SUM(COALESCE(WINS, 0)) + SUM(COALESCE(LOSSES, 0))) * 100 AS WIN_PERC,
                    0                                                                                    AS CRASHES,
                    000.00                                                                               AS OVERALL_WIN_PERC,
                    000.00                                                                               AS OVERALL_CRASH_PERC,
                    CONVERT_TZ(NOW(), @@SESSION.TIME_ZONE, '+00:00')                                     AS GENERATED_AT
    FROM STEP1_2
    GROUP BY BOT1,
             BOT2
    ORDER BY 1,
             2;
    DROP TEMPORARY TABLE IF EXISTS STATS_1;
    CREATE TEMPORARY TABLE STATS_1
    SELECT BOT1,
           BOT2,
           SUM(
                   CASE WHEN CR.TYPE = 'PLAYER1CRASH' THEN 1 ELSE 0 END
               ) BOT1_CRASHES,
           SUM(
                   CASE WHEN CR.TYPE = 'PLAYER2CRASH' THEN 1 ELSE 0 END
               ) BOT2_CRASHES
    FROM core_result CR
             LEFT JOIN PIVOT_1 K ON CR.ID = K.ID
    WHERE CR.TYPE IN ('PLAYER1CRASH', 'PLAYER2CRASH')
    GROUP BY BOT1,
             BOT2;
    DROP TEMPORARY TABLE IF EXISTS STATS_2;
    CREATE TEMPORARY TABLE STATS_2 LIKE STATS_1;
    INSERT INTO STATS_2
    SELECT *
    FROM STATS_1;
    DROP TEMPORARY TABLE IF EXISTS STATS_CRASHES;
    CREATE TEMPORARY TABLE STATS_CRASHES
    SELECT BOT_ID,
           SUM(BOT1_CRASHES) AS CRASHES
    FROM (
             SELECT BOT1 AS BOT_ID,
                    BOT1_CRASHES
             FROM STATS_1
             UNION
             SELECT BOT2 AS BOT_ID,
                    BOT2_CRASHES
             FROM STATS_2
         ) T
    GROUP BY BOT_ID;
    SET
        SQL_SAFE_UPDATES = 0;
    UPDATE STATS_BOT_PERC A
        INNER JOIN
        STATS_CRASHES B ON A.BOT_ID = B.BOT_ID
    SET A.CRASHES = B.CRASHES;
    DROP TEMPORARY TABLE IF EXISTS STATS_BOT_PERC_1;
    CREATE TEMPORARY TABLE STATS_BOT_PERC_1 LIKE STATS_BOT_PERC;
    INSERT INTO STATS_BOT_PERC_1
    SELECT *
    FROM STATS_BOT_PERC;
    UPDATE STATS_BOT_PERC A
        INNER JOIN
        (SELECT BOT_ID,
                SUM(WINS) / SUM(TOTAL_GAMES) * 100 AS OVERALL_WIN_PERC,
                CRASHES / SUM(TOTAL_GAMES) * 100      OVERALL_CRASH_PERC
         FROM STATS_BOT_PERC_1
         GROUP BY BOT_ID) K ON A.BOT_ID = K.BOT_ID
    SET A.OVERALL_WIN_PERC   = COALESCE(K.OVERALL_WIN_PERC, 0.00),
        A.OVERALL_CRASH_PERC = COALESCE(K.OVERALL_CRASH_PERC, 0.00);

    TRUNCATE TABLE core_statsbotmatchups;

    INSERT INTO core_statsbotmatchups(WIN_PERC,
                                      WIN_COUNT,
                                      GAME_COUNT,
                                      GENERATED_AT,
                                      BOT_ID,
                                      OPPONENT_ID)
    SELECT DISTINCT WIN_PERC,
                    WINS,
                    TOTAL_GAMES,
                    GENERATED_AT,
                    BOT_ID,
                    OPPONENT_ID
    FROM STATS_BOT_PERC
    WHERE WIN_PERC IS NOT NULL;

    TRUNCATE TABLE core_statsbots;
    INSERT INTO core_statsbots(WIN_PERC,
                               CRASH_PERC,
                               GAME_COUNT,
                               GENERATED_AT,
                               BOT_ID)
    SELECT DISTINCT OVERALL_WIN_PERC,
                    OVERALL_CRASH_PERC,
                    SUM(TOTAL_GAMES),
                    GENERATED_AT,
                    BOT_ID
    FROM STATS_BOT_PERC
    GROUP BY BOT_ID;
END
