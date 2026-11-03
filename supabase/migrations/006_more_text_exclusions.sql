-- 004 only caught titles starting with "Text". Cleveland also has "Page from ...: text page",
-- blank leaves, and folios titled just "...: Text". Mixed folios ("Scene (recto); Text (verso)") stay.
update artworks set excluded = 'manuscript text or blank page'
where source = 'cma' and excluded is null
  and title ~* '\mtext pages?\M|\mblank\M|^genealogical text|:\s*text\s*$';
