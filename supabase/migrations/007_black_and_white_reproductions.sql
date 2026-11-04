-- 120 Art Institute of Chicago records whose only image is a black-and-white reproduction. They have
-- zero chroma (95th percentile at most 0.005; the next-lowest painting in the collection is 3.44), so
-- they show no real palette. Records are kept. Clear `excluded` to bring one back.
update artworks set excluded = 'black-and-white reproduction'
where source = 'aic' and excluded is null and source_id in ('887', '15708', '5304', '2179', '20541', '16246', '19322', '53213', '53061', '881', '4092', '87531', '111427', '4896', '15279', '40507', '28143', '20697', '50309', '100348', '46383', '59858', '61642', '52177', '20597', '28857', '36519', '57652', '28136', '101781', '105698', '4096', '4800', '5355', '6793', '8610', '11022', '13447', '15303', '16192', '16349', '16389', '16413', '20419', '20526', '20542', '24677', '26217', '27170', '29403', '29437', '32086', '32094', '35180', '35195', '35253', '35256', '35259', '35280', '36508', '39492', '39493', '39528', '40381', '41208', '44770', '46076', '46382', '47181', '47588', '47596', '48535', '50306', '51582', '53488', '56556', '57727', '59004', '59006', '59882', '59907', '59930', '64412', '68428', '71771', '75392', '79584', '79789', '80213', '80348', '80535', '86232', '86236', '86441', '86904', '86994', '93737', '93784', '94123', '94124', '94239', '94842', '95108', '95613', '99653', '100343', '100344', '100353', '102089', '104107', '107836', '109426', '110767', '111057', '111616', '111626', '111650', '111652', '111663', '147451');

-- Drop their edges, and the edges of every painting that links to them. Then run
-- `python -m ingest.build_index` to recompute the missing edges.
delete from artwork_edges where source_id in (
  select e.source_id from artwork_edges e join artworks t on t.id = e.target_id
  where t.excluded = 'black-and-white reproduction');
delete from artwork_edges where source_id in (
  select id from artworks where excluded = 'black-and-white reproduction');
