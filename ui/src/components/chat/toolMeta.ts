/** Friendly names for the agent's tools, as shown in the activity lines. */
export const TOOL_LABELS: Record<string, [running: string, done: string]> = {
  service_status: ['Checking services', 'Checked services'],
  search_library: ['Searching your library', 'Searched your library'],
  series_details: ['Reading the series', 'Read the series'],
  movie_details: ['Reading the movie', 'Read the movie'],
  download_queue: ['Checking downloads', 'Checked downloads'],
  disk_usage: ['Checking disks', 'Checked disks'],
  wanted_missing: ['Looking for missing episodes', 'Found missing episodes'],
  lookup_title_to_add: ['Looking the title up', 'Looked the title up'],
  find_releases: ['Searching indexers', 'Searched indexers'],
  search_indexers: ['Searching all indexers', 'Searched all indexers'],
  judge_releases: ['Judging releases — reading files and live seeders', 'Judged releases'],
  inspect_release: ['Looking inside the release', 'Looked inside the release'],
  grab_release: ['Starting the download', 'Download started'],
  select_torrent_files: ['Selecting files', 'Selected files'],
  manual_import: ['Importing', 'Import planned'],
  add_series: ['Adding the series', 'Added the series'],
  add_movie: ['Adding the movie', 'Added the movie'],
  start_automatic_search: ['Starting a search', 'Search started'],
  delete_episode_files: ['Deleting episode files', 'Deleted episode files'],
  delete_movie_file: ['Deleting the movie file', 'Deleted the movie file'],
  list_torrents: ['Reading the torrent list', 'Read the torrent list'],
  torrent_files: ['Reading torrent files', 'Read torrent files'],
  remove_torrents: ['Removing torrents', 'Removed torrents'],
  search_titles: ['Searching the databases', 'Searched the databases'],
  title_details: ['Reading the title', 'Read the title'],
  recent_watch_history: ['Reading your history', 'Read your history'],
  taste_profile: ['Reading your taste', 'Read your taste'],
  recommend: ['Finding picks for you', 'Found picks'],
  adult_search: ['Searching StashDB', 'Searched StashDB'],
  adult_recommend: ['Finding scenes for you', 'Found scenes'],
  show_recommendations: ['Preparing your picks', 'Your picks'],
  whisparr_lookup: ['Searching Whisparr', 'Searched Whisparr'],
  whisparr_add: ['Adding to Whisparr', 'Added to Whisparr'],
  get_preferences: ['Reading preferences', 'Read preferences'],
  update_preferences: ['Saving preferences', 'Saved preferences'],
}

export function toolLabel(name: string, done: boolean): string {
  const labels = TOOL_LABELS[name]
  if (!labels) return name.replace(/_/g, ' ')
  return done ? labels[1] : labels[0]
}
