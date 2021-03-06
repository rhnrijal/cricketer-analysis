# Imports
import requests
import pandas as pd
from bs4 import BeautifulSoup
import numpy as np
import re
from .Match import Match


def total_balls(overs):
    '''Calculate total balls bowled from overs'''
    grouping_re = re.compile(r'^([0-9]*)\.([0-5]*)$').search(overs)
    if grouping_re is None:
        return(int(overs) * 6)
    else:
        overs = int(grouping_re.group(1)) * 6
        balls = int(grouping_re.group(2))
        return(overs + balls)

    
def helper_home_or_away(row):
    '''Calculate whether the match was played at home or away'''
    if row.home_team == 'Neutral':
        return('Neutral')
    elif row.opposition == row.home_team:
        return('Away')
    else:
        return('Home')
    
    
# Define the class for a player
class Cricketer:
    def __init__(self, player_id):
        self.id = str(player_id)
        if self.id:
            self.base_player_url = 'http://www.espncricinfo.com/ci/content/player/%s.html' % self.id
            self.test_innings_by_innings_url = 'http://stats.espncricinfo.com/ci/engine/player/%s.html?class=1;template=results;type=allround;view=innings' % self.id
            self.test_bowling_innings_url = 'http://stats.espncricinfo.com/ci/engine/player/%s.html?class=1;template=results;type=bowling;view=innings' % self.id

        if self.test_innings_by_innings_url:
            self.soup = BeautifulSoup(
                requests.get(
                    self.test_innings_by_innings_url).text,
                features="html.parser")

        if self.base_player_url:
            self.primary_team = BeautifulSoup(
                requests.get(
                    self.base_player_url).text, features="html.parser").find(
                'h3', {
                    'class': 'PlayersSearchLink'}).text
            self.player_details = self.get_player_details()

    def raw_innings(self):
        '''Search the raw html and return innings table'''
        for caption in self.soup.find_all('caption'):
            if caption.get_text() == 'Innings by innings list':
                main_table = caption.find_parent(
                    'table', {'class': 'engineTable'})

        columns = [header.get_text() for header in main_table.find(
            'thead').find_all('tr')[0].find_all('th')]
        rows = []

        for innings in [
                row for row in main_table.find('tbody').find_all('tr')]:
            rows.append([stat.get_text() for stat in innings.find_all('td')])

        return(pd.DataFrame(rows, columns=columns))

    def innings(self, include_match_urls=False):
        '''Clean raw_innings() and return pd.DataFrame'''
        raw_innings = self.raw_innings()
        raw_innings['Opposition'] = raw_innings['Opposition'].str.replace(
            'v ', '')
        raw_innings.replace('-', np.nan, inplace=True)

        # Clean the column names
        raw_innings.columns = raw_innings.columns.str.lower().str.replace(' ', '_')

        # Create boolean flags for various metrics
        raw_innings['is_out'] = raw_innings.score.astype('str').apply(
            lambda x: False if x in ['nan', 'DNB'] else False if '*' in x else True)
        raw_innings['did_bowl'] = raw_innings.overs.astype('str').apply(
            lambda x: False if x in ['nan', 'DNB'] else True)
        raw_innings['did_bat'] = raw_innings.score.str.replace(
            '*', '').astype('str').apply(lambda x: True if x.isnumeric() else False)
        raw_innings['score'] = raw_innings['score'].str.replace(
            '*', '')  # Remove the not out flag

        # Grab the main table
        for caption in self.soup.find_all('caption'):
            if caption.get_text() == 'Innings by innings list':
                main_table = caption.find_parent(
                    'table', {'class': 'engineTable'})

        # Grab the match id from the href
        raw_innings['match_id'] = [
            re.compile(r'match\/([0-9]*).html').search(
                x.get('href')).group(1) for x in main_table.find_all(
                'a', href=re.compile(r'.*engine\/match\/.*'))]

        # Get the match urls
        raw_innings['match_url'] = self.match_urls()

        # Create the final pd.DataFrame
        raw_innings = raw_innings[['inns',
                                   'score',
                                   'did_bat',
                                   'is_out',
                                   'overs',
                                   'conc',
                                   'wkts',
                                   'did_bowl',
                                   'ct',
                                   'st',
                                   'opposition',
                                   'ground',
                                   'start_date',
                                   'match_id',
                                   'match_url']]

        # Conditionall drop the match_url column
        drop_match_urls = not include_match_urls
        raw_innings.drop('match_url', inplace=drop_match_urls, axis=1)

        return(raw_innings)

    def batting_summary(self):
        '''Product summary statistics of entire career'''
        innings = self.innings()
        total_at_bats = innings.did_bat.sum()
        dismissals = innings.is_out.sum()
        total_runs = innings.score[innings.did_bat].dropna().astype(
            'int').sum()
        return(pd.DataFrame({'Innings': total_at_bats,
                             'Dismissals': dismissals,
                             'Total Runs': total_runs,
                             'Average': round(total_runs / dismissals, 4)}, index=['Overall']))

    def rolling_average_innings(self, n_innings):
        '''
        Return pd.DataFrame of rolling average at innings level

        Parameters:
        n_innings (int): the size of the rolling innings window
        '''
        innings = self.innings()[self.innings().did_bat].set_index(
            'start_date').loc[:, ['score', 'is_out']]
        innings.index = pd.to_datetime(innings.index)
        innings.score = innings.score.astype('int')
        rolling_innings = innings.rolling(n_innings).sum()
        rolling_innings['average'] = rolling_innings['score'] / \
            rolling_innings['is_out']
        return(rolling_innings)

    def rolling_average_matches(self, n_matches):
        '''
        Return pd.DataFrame of rolling average at match level

        Parameters:
        n_matches (int): the size of the rolling match window
        '''
        matches = self.innings()[self.innings().did_bat].set_index(
            'start_date').loc[:, ['score', 'is_out']]
        matches.score = matches.score.astype('int')
        matches.index = pd.to_datetime(matches.index)
        matches = matches.groupby('start_date').sum()
        rolling_matches = matches.rolling(n_matches).sum()
        rolling_matches['average'] = rolling_matches['score'] / \
            rolling_matches['is_out']
        return(rolling_matches)

    def accumulative_average(self):
        '''Calculate the average over time'''
        innings = self.innings()[self.innings().did_bat].set_index(
            'start_date').loc[:, ['score', 'is_out']]
        innings.index = pd.to_datetime(innings.index)
        innings.score = innings.score.astype('int')
        innings['total_runs'] = innings.score.cumsum()
        innings['total_dismissals'] = innings.is_out.astype('int').cumsum()
        innings['running_average'] = innings.total_runs / \
            innings.total_dismissals
        return(innings)

    def conversion(self):
        '''Calculate fifty/century conversion over time'''
        at_bats = self.innings()[self.innings().did_bat]
        at_bats['fifty'] = at_bats.score.astype(
            'int').between(50, 99, inclusive=True)
        at_bats['century'] = at_bats.score.astype('int').ge(100)
        at_bats.set_index('start_date', inplace=True)
        at_bats.index = pd.to_datetime(at_bats.index)
        conversion = at_bats[['fifty', 'century']].astype('int').cumsum()
        conversion['rate'] = conversion['century'] / \
            (conversion['fifty'] + conversion['century'])
        return(conversion)

    def yearly_conversion(self):
        '''Calculate fifty/century conversion for every calendar year of the career'''
        at_bats = self.innings()[self.innings().did_bat]
        at_bats['fifty'] = at_bats.score.astype(
            'int').between(50, 99, inclusive=True)
        at_bats['century'] = at_bats.score.astype('int').ge(100)
        at_bats.set_index('start_date', inplace=True)
        at_bats.index = pd.to_datetime(at_bats.index)
        yearly = at_bats[['fifty', 'century']].astype(
            'int').resample('A').sum()
        yearly['rate'] = yearly['century'] / \
            (yearly['fifty'] + yearly['century'])
        return(yearly)

    def acc_yearly_conversion(self):
        '''Accumulative version of yearly_conversion()'''
        ot = self.yearly_conversion()[['fifty', 'century']].cumsum()
        ot['rate'] = ot['century'] / (ot['fifty'] + ot['century'])
        return(ot)

    def match_urls(self):
        '''Find and generate absolute links to all matches'''
        for caption in self.soup.find_all('caption'):
            if caption.get_text() == 'Innings by innings list':
                main_table = caption.find_parent(
                    'table', {'class': 'engineTable'})

        base_url = 'https://www.espncricinfo.com'
        match_links = [
            base_url +
            x.get('href') for x in main_table.find_all(
                'a',
                href=re.compile(r'.*engine\/match\/.*'))]
        return(match_links)

    def get_test_matches(self):
        '''Create Match objects for every match in the innings by innings list'''
        matches = {}

        # Loop through the distinct match urls and save to dictionary
        for match_url in set(self.match_urls()):
            obj = Match(match_url)
            matches[obj.id] = obj

        return(matches)

    def test_bowling_innings(self):
        soup = BeautifulSoup(
            requests.get(
                self.test_bowling_innings_url).text,
            features="html.parser")
        for caption in soup.find_all('caption'):
            if caption.get_text() == 'Innings by innings list':
                main_table = caption.find_parent(
                    'table', {'class': 'engineTable'})

        all_table_rows = main_table.find_all('tr')
        columns = [
            h.text.lower().replace(
                ' ', '_') for h in main_table.find(
                'tr', {
                    'class': 'headlinks'}).find_all('th')]
        rows_raw = [[y.text for y in x.find_all(
            'td')] for x in all_table_rows if x.find_all('td') != []]

        # Find the links to each match
        match_links = [
            x.find(
                'a', {
                    'title': 'view the scorecard for this row'}) for x in main_table.find_all('tr')]
        match_urls = ['http://www.espncricinfo.com/' +
                      x.get('href') for x in match_links if x is not None]
        df_1 = pd.DataFrame(
            rows_raw, columns=columns).drop(
            '', axis=1).set_index('start_date')

        match_urls_df = pd.DataFrame(match_urls, columns=['match_url'])
        match_urls_df.index = df_1.index
        df = pd.concat([df_1, match_urls_df], axis=1)
        df.index = pd.to_datetime(df.index)  # Change the index to datetime

        # Remove the innings where the cricketer didn't bowl
        df = df[df.overs != 'DNB']
        df = df[df.overs != 'TDNB']
        
        # Convert types and clean columns
        df.wkts = df.wkts.astype(int)
        df.runs = df.runs.astype(int)
        df.mdns = df.mdns.astype(int)
        df.pos = df.pos.astype(int)
        df.inns = df.inns.astype(int)
        df.opposition = df.opposition.str.replace('v ', '')

        # Convert the overs notation to total balls bowled
        df['total_balls'] = df.overs.apply(total_balls)

        # Pull and store match object
        df['match_obj'] = df.match_url.apply(Match)

        # Work out whether game was home or away
        df['home_team'] = [x.home_team_name for x in df.match_obj]
        df['home_or_away'] = df.apply(helper_home_or_away, axis = 1)

        return(df)

    def get_player_details(self):
        '''Get the player roles and styles from the base_url'''
        player2soup = BeautifulSoup(
            requests.get(
                self.base_player_url).text,
            features="html.parser")

        details = {}
        for detail in player2soup.find_all(
                'p', {'class': 'ciPlayerinformationtxt'}):
            if detail.find('b').text in [
                'Playing role',
                'Batting style',
                    'Bowling style']:
                details[detail.find('b').text] = detail.find('span').text

        return(details)