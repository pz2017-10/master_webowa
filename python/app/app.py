from flask import Flask, render_template, json, request, redirect, session
from flaskext.mysql import MySQL
from collections import OrderedDict
import random

mysql = MySQL()
app = Flask(__name__)

# konfiguracje MySQL:
app.config['MYSQL_DATABASE_USER'] = 'pz2017_10'
app.config['MYSQL_DATABASE_PASSWORD'] = 'vV8bdtj2fGMhaG2u'
app.config['MYSQL_DATABASE_DB'] = 'pz2017_10'
app.config['MYSQL_DATABASE_HOST'] = 'localhost'
app.config['MYSQL_DATABASE_PORT'] = 5432
app.secret_key = '329743bjshads93982472463246sas'
mysql.init_app(app)

def is_power2(n):
    """
    Funkcja sprawdzająca czy podana liczba jest potęgą dwójki.
    Używana przy tworzeniu nowego turnieju w metodzie /newTournament

    """
    return n != 0 and ((n & (n - 1)) == 0)

def getUserMatches(login, a):
    """
    Funkcja pobiera login użytkownika, zwraca listę rozegranych przez niego meczy zaczynając w kolejności od
    meczy rozegranych. Każdy mecz jest zapisany na liście w postaci słownika:
                { 'przeciwnik' - login przeciwnika
                  'data' - data rozegrania meczu
                  'punkty_moje' - informacje o zdobytych punktach w każdym secie przez gracza
                  'punkty_przeciwnika' - informacje o zdobytych punktach w każdym secie przez przeciwnika
                  'przebieg_meczu' - zmienna z informacją o zdobytym każdym pojedynczym punkcie w każdym secie
                  'wynik_meczu' - ogólny wynik meczu w setach
                  'id_turnieju' - numer id turnieju
                  }
    """

    con = mysql.connect()  # łączenie z bazą danych
    cursor = con.cursor()
    cursor.callproc('sp_getRozegraneMecze', (login,))  # wywołanie procedury SQL, która pobiera mecze uzytkownika
    dane = cursor.fetchall() # pobrane z bazy dane zawiera liste meczy zalogowanego uzytkownika
    ilosc_meczow = len(dane)
    dane = dane[(a*8):(a*8)+8]
    # struktura pobranego meczu: {id_meczu, ..., login1, login2}
    con.commit()

    mecze = [ilosc_meczow,]
    for m in dane:  # dla kazdego meczu zalogowanego uzytkownika
        data = m[4]  # zapisanie daty rozegrania meczu, jeżeli jest None to mecz się nie odbył
        id_meczu = m[0]
        id_turnieju = m[1]
        wynik_meczu = [0, 0]  # jeżeli mecz się nie odbył, domyślna wartość wyniku meczu to 0:0

        # pozostałe zmienne, które będą przechowywać dane meczu
        punkty_moje = {}
        punkty_przeciwnika = {}
        przebieg_meczu = []

        if m[2] == login:  # sprawdzanie, który gracz jest zalogowanym, a który jego przeciwnikiem w tym meczu
            przeciwnik = m[3]
        else:
            przeciwnik = m[2]

        # pobieranie informacji o punktach w meczu:
        p_set = []  # zmienna pomocnicza przechowująca informacje o pojedyńczym secie
        if data:  # jeżeli mecz się odbył pobieram dane o punktach w tym meczu:
            # wywołanie w bazie procedury ktora dla danego meczu zwraca dane o punktach:
            cursor.callproc('sp_getPunkty', (id_meczu,))
            dane2 = cursor.fetchall()  # pobrane z bazy dane zawieraja loginy graczy ktorzy zdobyli pojedynczy punkt

            for j in dane2:  # zliczanie punktów dla obu graczy
                if j[0] not in punkty_moje:  # jeśli punkty dla tego setu nie są jeszcze liczone
                    punkty_moje[j[0]] = 0  # punkty dla tego setu ustawiam na 0
                    punkty_przeciwnika[j[0]] = 0
                    przebieg_meczu.append(p_set)  # do przebiegu meczu dodaję poprzedni set
                    p_set = []  # tworze nowy pusty set, ktory bedzie zawieral przebieg gry
                if j[1] == login:  # jeśli punkt zdobył gracz1 to dodaje mu punkt w tym secie
                    punkty_moje[j[0]] += 1
                    p_set.append(1)
                elif j[1] == przeciwnik:  # dodaje punkt przeciwnikowi
                    punkty_przeciwnika[j[0]] += 1
                    p_set.append(0)
            przebieg_meczu.append(p_set)  # dodaję do przebiegu meczu ostatni set
            przebieg_meczu = przebieg_meczu[1:]  # usuwam pusty set z początku liczenia przebiegu meczu

            # obliczanie wyniku meczu
            for j in range(len(punkty_moje)):  # sumowanie wygranych setów do ostatecznego wyniku meczu
                if punkty_moje[j + 1] > punkty_przeciwnika[j + 1]:
                    wynik_meczu[0] += 1
                elif punkty_moje[j + 1] < punkty_przeciwnika[j + 1]:
                    wynik_meczu[1] += 1
        mecze.append({'przeciwnik': przeciwnik,
                  'data': data,
                  'punkty_moje': punkty_moje,
                  'punkty_przeciwnika': punkty_przeciwnika,
                  'przebieg_meczu': przebieg_meczu,
                  'wynik_meczu': wynik_meczu,
                  'id_turnieju': id_turnieju,
                  })
    con.commit()
    cursor.close()  # zamykam połączenie z bazą danych
    con.close()
    return mecze

def getTournamentDetails(id_turnieju):
    """
    Funkcja pobiera id turnieju i zwraca slownik zawierający dane o turnieju:
        {
        'id'        - id turnieju
        'nadzorca'  - nadzorca, czyli gracz, który utworzył turniej
        'typ'       - typ turnieju (ligowy lub pucharowy)
        'opis'      - opis turnieju
        'mecze'     - lista ze szczegółowymi danymi o meczach tego turnieju
        'rundy'     - poszczególne etapy turnieju pucharowego, zmienna potrzebna do zbudowania drzewa turnieju
        'ranking'   - ranking najlepszych uczestników turnieju
        'tabela'    - dane potrzebne do zbudowania tabeli wyników meczu ligowego
        }
    """
    con = mysql.connect() # połączenie z bazą danych
    cursor = con.cursor()
    cursor.callproc('sp_getTurniej', (id_turnieju,))  # pobieranie z bazy podstawowych danych o turnieju
    dane3 = cursor.fetchall() # dane o turnieju

    cursor.callproc('sp_getMeczTurnieju', (id_turnieju,))  # pobieram mecze turnieju o danym id
    dane2 = cursor.fetchall() # mecze turnieju
    con.commit()


    # uzupełnienie podstawowych informacji o turnieju do zmiennych:
    id = dane3[0][0]
    nadzorca = dane3[0][5]
    typ = dane3[0][3]
    opis = dane3[0][4]
    mecze = []
    mecze2 = []

    for k in dane2:  # dla każdego z meczy wydobywam informacje z bazy i dodaje do listy meczy 'mecze = []'
         # zmienna punkty_meczu zawiera informacje czy uzytkownik zdobyl, czy stracil punkt [[1, 1 ,0, 0, 0,...], ...]
        przebieg_meczu = []

        # zmienne beda przechowywac dla kazdego setu ilosc zdobytych punktow przez gracza
        punkty_gracz1 = {}
        punkty_gracz2 = {}
        p_set = []
        data = k[4]
        gracz1 = k[2]
        gracz2 = k[3]
        wynik_meczu = [0, 0]  # zmienna przechowuje ilosc wygranych setow przez obu graczy

        if data:  # jeżeli mecz się odbył
            cursor.callproc('sp_getPunkty', (k[0],))  # pobieram informacje o punktach danego meczu
            dane4 = cursor.fetchall()
            con.commit()
            for j in dane4:  # zliczam punkty dla obu graczy
                if j[0] not in punkty_gracz1:  # jesli punkty dla tego setu nie sa liczone
                    punkty_gracz1[j[0]] = 0  # punkty dla tego setu ustawiam na 0
                    punkty_gracz2[j[0]] = 0
                    przebieg_meczu.append(p_set)  # do przebiegu meczu dodaje poprzedni set
                    p_set = []  # tworze pusty set, ktory bedzie zawieral przebieg gry [0, 1, 1, 0, ...]
                if j[1] == k[2]:  # jesli punkt zdobyl gracz1 to dodaje mu punkt w tym secie
                    punkty_gracz1[j[0]] += 1
                    p_set.append(1)
                elif j[1] == k[3]:
                    punkty_gracz2[j[0]] += 1
                    p_set.append(0)
            przebieg_meczu.append(p_set)
            przebieg_meczu = przebieg_meczu[1:]

            for j in range(len(punkty_gracz1)):
                if punkty_gracz1[j + 1] > punkty_gracz2[j + 1]:
                    wynik_meczu[0] += 1
                elif punkty_gracz1[j + 1] < punkty_gracz2[j + 1]:
                     wynik_meczu[1] += 1

            mecze.append({
                'gracz1': gracz1,
                'gracz2': gracz2,
                'data': data,
                'punkty_gracz1': punkty_gracz1,
                'punkty_gracz2': punkty_gracz2,
                'przebieg_meczu': przebieg_meczu,
                'wynik_meczu': wynik_meczu,
                'id': k[0],

            })
        else:
            mecze2.append({
                'gracz1': gracz1,
                'gracz2': gracz2,
                'data': data,
                'punkty_gracz1': punkty_gracz1,
                'punkty_gracz2': punkty_gracz2,
                'przebieg_meczu': przebieg_meczu,
                'wynik_meczu': wynik_meczu,
                'id': k[0],
            })
    con.commit()
    cursor.close() # zamknięcie połączenia z bazą danych
    con.close()

    mecze = mecze + mecze2
    # pozostałe zmienne, które będą przechowywać dane o turnieju
    ranking = {}
    rundy = []
    tabela = []

    zakonczony = True # zmienna pomocnicza mówiąca o tym czy w turnieju rozegrane zostały wszystkie mecze
    gracze = set() # zmienna pomocnicza zawierać będzie loginy graczy biorących udział w turnieju

    for mecz in mecze: # przeglądam każdy mecz turnieju
        if mecz['data'] == None: # sprawdzam czy turniej się zakończył:
            zakonczony = False
        gracze.add(mecz['gracz1']) # tworzę zbiór z loginami graczy biorących udział w turnieju
        gracze.add(mecz['gracz2'])
    ilosc_graczy = len(gracze) # zapisuję do zmiennej ilość graczy biorących udział w turnieju

    if typ == 'pucharowy': # dla turnieju pucharowego:
        mecze2 = sorted(mecze, key=lambda x: x['id']) # sortuje mecze w kolejności ich utworzenia
        runda = [] # zmienna pomocnicza zawiera mecze danego etapu turnieju pucharowego
        gracze = set() # czyszczę zmienną pomocniczą
        for mecz in mecze2[:ilosc_graczy - 1]: # przeglądam mecze turnieju pomijając dogrywki o trzecie miejsce
            if ((mecz['gracz1'] or mecz['gracz2']) in gracze): # sprawdzam w ten sposób czy mecz należy do kolejnego etapu
                gracze = set() # czyszczę zmienną pomocniczą
                # sprawdzanie czy gracze już grali w tym etapie pomaga odróżnić etapy turnieju pucharowego
                gracze.add((mecz['gracz1'], mecz['gracz2']))
                rundy.append(runda) # do całości dodaję mecze ostatnio zapisanego etapu
                if(runda[0]['gracz1'] != mecz['gracz1']): # zamieniam graczy miejscami aby prawidlowo rysowac drzewo turnieju
                    mecz['gracz1'], mecz['gracz2'] = mecz['gracz2'], mecz['gracz1']
                    mecz['wynik_meczu'][0], mecz['wynik_meczu'][1] = mecz['wynik_meczu'][1], mecz['wynik_meczu'][0]
                runda = [mecz] # do nowego etapu zapisuję bieżący mecz
            else: # jeżeli mecz należy ciągle do tego samego etapu
                gracze.add(mecz['gracz1']) # wypełniam zmienne pomocnicze
                gracze.add(mecz['gracz2'])
                runda.append(mecz) # do bieżącego etapu wstawiam dany mecz
            # ranking dla turnieju pucharowego:
            if zakonczony == True: # jeżeli turniej zakończył się to obliczam ranking najlepszych uczestników:
                if mecz['gracz1'] not in ranking:
                    ranking[mecz['gracz1']] = mecz['wynik_meczu'][0]
                else:
                    ranking[mecz['gracz1']] += mecz['wynik_meczu'][0]

                if mecz['gracz2'] not in ranking:
                    ranking[mecz['gracz2']] = mecz['wynik_meczu'][1]
                else:
                    ranking[mecz['gracz2']] += mecz['wynik_meczu'][1]

        rundy.append(runda) # dodaję po pętli for ostatni etap do listy etapów turnieju

        # jeśli odbywały się jakieś dodatkowe mecze (dogrywki o trzecie miejsce) to uwzgledniam kto wygrał dogrywkę
        if (zakonczony == True) and (len(mecze) > (ilosc_graczy - 1)):
            for m in mecze2[ilosc_graczy - 1:]:
                if m['wynik_meczu'][0] > m['wynik_meczu'][1]:
                    ranking.pop(m['gracz2'])
                else:
                    ranking.pop(m['gracz1'])

        ranking = OrderedDict(sorted(ranking.items(), key=lambda x: x[1], reverse=True)) # sortuję ranking

    elif typ == 'ligowy': # jeżeli turniej jest ligowym:
        wiersz = ['']  # zmienna pomocnicza zawierać będzie dane potrzebne do tabeli turnieju ligowego

        for mecz in mecze:
            if mecz['gracz1'] not in ranking:
                ranking[mecz['gracz1']] = mecz['wynik_meczu'][0]
            else:
                ranking[mecz['gracz1']] += mecz['wynik_meczu'][0]

            if mecz['gracz2'] not in ranking:
                ranking[mecz['gracz2']] = mecz['wynik_meczu'][1]
            else:
                ranking[mecz['gracz2']] += mecz['wynik_meczu'][1]

        ranking = OrderedDict(sorted(ranking.items(), key=lambda x: x[1], reverse=True))  # sortowanie rankingu

        # obliczenia do listy 'tabela' potrzebne do stworzenia tabeli turnieju ligowego
        for gracz in ranking:  # dla każdego gracza zaczynając od najlepszych
            wiersz.append(gracz)  # wypełniam pierwszy wiersz loginami uczestników turnieju
        tabela.append(wiersz)  # dodaję wiersz do tabeli
        wiersz = []  # czyszczę zmienną pomocniczą zawierającą pojedyńczy wiersz tabeli
        for gracz1 in ranking:  # dla każdego uczestnika trunieju
            wiersz.append(gracz1)  # zaczynam wypełniać wiersz zaczynając od loginu uczestnika
            for gracz2 in ranking:  # przeglądam kolejny raz po uczestnikach turnieju
                if gracz1 == gracz2:  # w miejscu tabeli dla tego samego gracza wstawiam ---
                    wynik = '#'
                    wiersz.append(wynik)  # dodaję wynik do aktualnego wiersza
                else:  # dla pary graczy w tabeli
                    for mecz in mecze:  # szukam meczu, który rozegrała para graczy
                        # wpisuję do tabeli wyniki graczy
                        if mecz['gracz1'] == gracz1 and mecz['gracz2'] == gracz2:
                            if mecz['wynik_meczu'] == [0,0]:
                                wiersz.append(' - ')
                            else:
                                wynik = str(mecz['wynik_meczu'][0]) + ':' + str(mecz['wynik_meczu'][1])
                                wiersz.append(wynik)
                        elif mecz['gracz1'] == gracz2 and mecz['gracz2'] == gracz1:
                            if mecz['wynik_meczu'] == [0,0]:
                                wiersz.append(' - ')
                            else:
                                wynik = str(mecz['wynik_meczu'][1]) + ':' + str(mecz['wynik_meczu'][0])
                                wiersz.append(wynik)
            tabela.append(wiersz)  # do tabeli dodaję bieżący wiersz
            wiersz = []  # czyszczę pomocniczą zmienną przechowującą pojedyńczy wiersz tabeli

    return { # zwracam dane turnieju
        'id': id,
        'nadzorca': nadzorca,
        'typ': typ,
        'opis': opis,
        'mecze': mecze,
        'rundy': rundy,
        'ranking': ranking,
        'tabela': tabela,
        'zakonczony' : zakonczony,
    }

@app.route("/")
def main():
    """
    Metoda odpowiedzialna za wyświetlanie strony domowej zalogowanego użytkownika, zaś dla niezalogowanego,
    wyświetlona zostaje strona do logowania bądź rejestracji.
    """
    if session.get('user'):
        return redirect('userHome')
    else:
        return render_template('index.html')

@app.route('/showSignUp')
def showSignUp():
    """
    Metoda wyświetla stroną z formularzem do zalogowania się. W przypadku zalogowanego użytkownika, zwróci jego stronę
    domową.

    """
    if session.get('user'):
        return redirect('userHome')
    else:
        return render_template('signup.html')

@app.route('/signUp', methods=['POST'])
def signUp():
    """
    Metoda odpowiedzialna za pobranie danych o rejestracji z formularza, walidację danych i wyświetlenie informacji
    o utworzeniu bądź nieutworzeniu konta.

    """
    # czytanie wartosci z formularza rejestracji uzytkownika
    p_login = request.form['inputName']
    p_email = request.form['inputEmail']
    p_haslo = request.form['inputPassword']

    # walidacja:
    if p_login and p_email and p_haslo:

        # Jesli wszystko ok, lacze sie z baza danych:
        conn = mysql.connect()
        cursor = conn.cursor()
        cursor.callproc('sp_createUser', (p_login, p_email, p_haslo))
        data = cursor.fetchall()
        conn.commit() # zamknięcie połączenia
        cursor.close()
        conn.close()

        if len(data) is 0: # po pomyślnej rejestracji wyświetla stronę logowania.
            return render_template('signin.html', info2='Konto zostało utworzone. Możesz teraz się zalogować.')
        else: # w przeciwnym razie wyświetla się pod formularzem rejestracji informacja o niepowodzeniu.
            return render_template('signup.html', info='Nie udało się założyć konta.')
    else:
        return json.dumps({'html': '<span>Wypełnij pola</span>'})

@app.route('/showSignIn')
def showSignin():
    """
    Metoda odpowiada za wyświetlenie strony z formularzem do logowania, w przypadku gdy użytkownik jest już zalogowany,
    wyświetla jego stronę domową.
    """

    if session.get('user'):
        return redirect('userHome')
    else:
        return render_template('signin.html')

@app.route('/validateLogin', methods=['POST'])
def validateLogin():
    """
    Metoda wykonywana po wypełnieniu formularza logowania, przeprowadza walidację danych i w zależności od poprawności
    danych wyświetla stronę domową użytkownika lub informację o nieudanym zalogowaniu się.
    """

    # Pobieranie danych z formularza strony signin.html
    p_login = request.form['inputName']
    p_haslo = request.form['inputPassword']

    con = mysql.connect() # połączenie z bazą danych
    cursor = con.cursor()
    cursor.callproc('sp_validateLogin', (p_login,)) # uruchomienie w bazie procedury walidacji danych logowania
    data = cursor.fetchall() # pobranie informacji z wywołąnej procedury
    con.commit() # zamknięcie połączenia z bazą danych
    cursor.close()
    con.close()

    if len(data) > 0:
        if str(data[0][2]) == p_haslo:
            # zalogowanie użytkownika oraz wyświetlenie jego strony domowej.
            session['user'] = data[0][0]
            return redirect('/userHome')
        else:
            # wyświetlenie ponownie formularza logowania z informacją o niepowodzeniu.
            return render_template('signin.html', info="Podano złe dane logowania.")
    else:
        return render_template('signin.html', info="Podano złe dane logowania.")

@app.route('/userHome')
def userHome():
    """
    Metoda wyświetla stronę domową zalogowanego użytkownika. Strona userHome.html zawiera podstawowe statystyki
    gracza, ostatnio rozegrane mecze oraz listę zaplanowanych meczy.
    """
    #jesli uzytkownik poprawnie sie zalogowal
    if session.get('user'):
        login = session.get('user') #zmienna zawiera login zalogowanego uzytkownika

        #STATYSTYKI
        con = mysql.connect() # łączenie z baza danych
        cursor = con.cursor()
        cursor.callproc('sp_getNierozegraneMecze', (login,)) #wywoluje procedure SQL, ktora pobiera mecze uzytkownika
        zaplanowane = cursor.fetchall()
        con.commit()

        # wywołuję procedurę sql która zwraca ilość wygranych meczy i zapisuję tą informację do zmiennej 'wygranych'
        cursor.callproc('sp_getWinners',)
        wygrane = cursor.fetchall()
        con.commit() # zamykam połączenie z bazą danych

        # wywołuję procedurę w bazie, która zwraca ilość rozegranych meczy użytkownika
        cursor.callproc('sp_getIloscRozegranychMeczy', (login,))
        rozegranych = cursor.fetchall()[0][0]
        cursor.close()
        con.close()

        # wydobywam szczegóły o ostatnich trzech rozegranych meczach i zapisuję te informacje do listy 'mecze'
        ostatnie_mecze = getUserMatches(login, 0)[1:4]

        for i in wygrane:
            if i[0] == login:
                wygranych = i[1]

        # zapisuję statystyki gracza do słownika
        statystyki={
            'rozegranych' : rozegranych,
            'wygranych' : wygranych,
            'nierozegranych' : len(zaplanowane),
        }

        # zapisuję do listy 'zaplanowane_mecze' informacje o nierozegranych meczach turniejowych.
        zaplanowane_mecze=[]
        for i in zaplanowane:
            if i[2] == login: # uwzględniam przeciwika i zapisuję jego login.
                przeciwnik = i[3]
            else:
                przeciwnik = i[2]

            zaplanowane_mecze.append({ # słownik zawiera dla każdego nierozegranego meczu id_turnieju oraz login przeciwnika
                'przeciwnik' : przeciwnik,
                'id_turnieju' : i[1],
            })

        zdarzenia={ # słownik który zawiera wszystkie zebrane informacje o meczach
            'ostatnie_mecze' : ostatnie_mecze,
            'nierozegrane_mecze' : zaplanowane_mecze,
        }

        # przekazuje zmienne do wyswietlenia na stronie domowej użytkownika
        if len(statystyki):
            return render_template('userHome.html', login=login, statystyki=statystyki, zdarzenia=zdarzenia)
        else:
            return render_template('info.html', info='Brak danych', login=login)
    else:
        return redirect('/showSignUp') # jeżeli użytkownik się nie zalogował następuje przekierowanie

@app.route('/myMatches/<int:a>')
def myMatches(a):
    """
    Metoda ta wyświetla wszystkie rozegrane mecze zalogowanego gracza w raz ze szczegółowymi informacjami.
    Korzysta z funkcji getUserMatches().
    """

    #jesli uzytkownik poprawnie sie zalogowal
    if session.get('user'):
        login = session.get('user') # zmienna zawiera login zalogowanego uzytkownika
        mecze = getUserMatches(login, a) # pobieram dane o meczach
        ilosc_meczow = mecze[0] # pierwsza wartosc zawiera liczbę ilości meczy
        mecze = mecze[1:] # obcinam liste meczy o pierwszą wartość z ilościom wszystkich meczy

        # przekazuję dane o meczach i wyświetlam w stronie myMatches.html
        return render_template('myMatches.html', login=login, mecze=mecze, a=a, ilosc_meczow=ilosc_meczow)
    else:
        return redirect('/showSignUp')

@app.route('/showTournamentForm/<string:info>')
def showTournamentForm(info):
    """
    Metoda odpowiedzialna jest za zgromadzenie listy użytkowników zarejestrowanych w systemie i przekazanie tej listy
    do formularza tworzenia nowego turnieju. Korzysta z procedury bazodanowej 'sp_getUsers'
    """

    if session.get('user'): # jeżeli użytkownik poprawnie się zalogował
        # tworze listę loginów wszystkich użytkowników
        uzytkownicy = [] # zmienna będzie listą wszystkich użytkowników w systemie
        con = mysql.connect() # łącze z bazą danych
        cursor = con.cursor()
        cursor.callproc('sp_getUsers', ()) # wywołuję procedurę aby pobrać listę użytkowników
        dane = cursor.fetchall()
        con.commit() # zamykam połaczenie z bazą
        cursor.close()
        con.close()

        # W przypadku błędu we wcześniejszym tworzeniu turnieju, pod formularzem wyświetlam komunikat.
        if info == 'err1':
            info = 'Nie utworzono turnieju!'
        elif info == 'err2':
            info = 'Zla liczba uczestnikow. W turnieju pucharowym liczba uczestników musi wynosić 2^n'
        else:
            info = ''

        for i in dane: # dodaję użytkowników do listy
            uzytkownicy.append(i[0])

        # wyświetlam formularz do utworzenia nowego turnieju
        return render_template('newTournament.html', nadzorca=session.get('user'), uzytkownicy=uzytkownicy, info=info)
    else:
        return render_template('signin.html')

@app.route('/newTournament',  methods=['POST', 'GET'])
def newTournament():
    """
    Metoda pobiera z formularza nowego turnieju dane o turnieju oraz tworzy turniej w bazie oraz tworzy mecze.

    """
    if session.get('user'): # jeżeli użytkownik poprawnie się zalogował
        #pobieram z formularza: do_ilu_punkty, do_ilu_sety, typ, opis
        p_uczestnicy = request.form.getlist('inputGracze')
        p_punkty = request.form['inputPunkty']
        p_sety = request.form['inputSety']
        p_typ = request.form.get('inputTyp')
        p_opis = request.form['inputOpis']
        p_login = session.get('user')

        if p_punkty and p_sety and p_typ and p_login: # sprawdzam czy pola były wypełnione
            liczba_uczestnikow = len(p_uczestnicy) # zapisuję ilość uczestników turnieju
            pary = []  # zmienna bedzie zawierac pary graczy ktorzy beda rozgrywac mecz
            if p_typ == 'ligowy': # w zależności od typu tunieju
                # Tworze turniej w bazie danych z pomocą procedury SQL
                con = mysql.connect()
                cursor = con.cursor()
                cursor.callproc('sp_newTurniej', (p_punkty, p_sety, p_typ, p_opis, p_login))  #
                id_turnieju = cursor.fetchall()  # pobieram id nowo utworzonego turnieju
                con.commit()
                #tworze pary uczestnikow ktorzy beda razem grac ze soba mecze "kazdy z kazdym" - LIGOWY
                for i in range(liczba_uczestnikow - 1):
                    for j in range(liczba_uczestnikow - 1 - i):
                        para = []
                        para.append(p_uczestnicy[i])
                        para.append(p_uczestnicy[j+i+1])
                        pary.append(para)
                random.shuffle(pary) # losowa kolejność na liscie meczy
                info = 'Utworzono Turniej ligowy' # zapisuję do zmiennej informacje o utworzeniu turnieju

            elif p_typ == 'pucharowy':  #PUCHAROWY
                if is_power2(liczba_uczestnikow)==True: # sprawdzam czy liczba użytkowników jest odpowiednia
                    random.shuffle(p_uczestnicy)
                    # Tworze turniej w bazie danych z pomocą procedury SQL
                    con = mysql.connect()
                    cursor = con.cursor()
                    cursor.callproc('sp_newTurniej', (p_punkty, p_sety, p_typ, p_opis, p_login))  #
                    id_turnieju = cursor.fetchall()  # pobieram id nowo utworzonego turnieju
                    con.commit()
                    for i in range(int(liczba_uczestnikow / 2)): # tworzę pary użytkowników grających mecze
                        para = []
                        para.append(p_uczestnicy[i])
                        para.append(p_uczestnicy[liczba_uczestnikow - i - 1])
                        pary.append(para)
                    info = 'Utworzono Turniej pucharowy' # zapisuję do zmiennej informację o utworzeniu meczu
                else:
                    # liczba graczy w turnieju pucharowym musi być 2^n
                    return redirect('/showTournamentForm/err2')

            #wywoluje procedure SQL w bazie, ktora tworzy pojedyncze mecze dla turnieju:

            for i in pary: # tworzę w bazie mecze dla turnieju
                cursor.callproc('sp_newMecz', (id_turnieju, i[0], i[1]))
                con.commit()
        else:
            return redirect('/showTournamentForm/err1')

        # pobieram informacje o turniejach zalogowanego użytkownika
        cursor.callproc('sp_getTurniejeIdGracza', (p_login,))
        dane = cursor.fetchall()
        dane = sorted(dane, key=lambda x: x, reverse=True)
        ilosc_turniejow = len(dane)
        turnieje = []
        for i in dane:
            turnieje.append(getTournamentDetails(i))
        con.commit()
        cursor.close()
        con.close()
        # wyĹ›wietlam stronÄ™ z turniejami uĹĽytkownika wraz z informacjÄ… o utworzeniu nowego turnieju
        return render_template('myTournaments.html', info=info, turnieje=turnieje, login=session.get('user'), a=0,
                               ilosc_turniejow=ilosc_turniejow)
    else:

        return render_template('signin.html')

@app.route('/showTournament/<int:id>', methods=['GET'])
def showTournament(id):
    """
    Metoda pobiera id turnieju i wyświetla stronę z informacjami o tym turnieju. Korzysta z funkcji getTournamentDetails
    """

    turniej = getTournamentDetails(id) # pobieram dane o turnieju

    # przekazuję dane do strony tournament.html i wyświetlam.
    return render_template('tournament.html',turniej=turniej, login=session.get('user'))

@app.route('/myTournaments/<int:a>')
def myTournaments(a):
    """
    Metoda odpowiada za pobranie danych o wszystkich turniejach zalogowanego gracza i wyświetleniu ich.
    Korzysta z funkcji getTournamentDetails() oraz procedury w bazie danych: 'sp_getTurniejeIdGracza'
    """
    if session.get('user'): # jeżeli gracz jest zalogowany:
        login = session.get('user') #zmienna zawiera login zalogowanego uzytkownika

        con = mysql.connect() #lacze z baza danych
        cursor = con.cursor()
        cursor.callproc('sp_getTurniejeIdGracza', (login,))
        dane=cursor.fetchall() # pobieram z bazy danych id turniejów w któ©ych brał udział
        ilosc_turniejow = len(dane)
        dane = sorted(dane, key=lambda x: x, reverse=True)
        dane = dane[(a*5):(a*5)+5] # zmniejszam dane do pięciu turniejów
        con.commit()
        cursor.close()
        con.close() # zmaykam połączenie z bazą danych.

        turnieje = [] #zmienna bedzie zawierac listę turnieji
        for i in dane:  #zapisuję dane o turniejach do listy turnieje[]
            turnieje.append(getTournamentDetails(i))

        # przekazuję do wyświetlenia informacje o wszystkich meczech gracza
        return render_template('myTournaments.html', turnieje = turnieje, login=session.get('user'), a=a,
                               ilosc_turniejow=ilosc_turniejow)
    return render_template('signin.html')

@app.route('/deleteTournament/<int:id>', methods=['GET'])
def deleteTournament(id):
    """
    Metoda pobiera id turnieju i usuwa go z bazy danych.
    Korzysta z procedury w bazie danych: 'sp_getTurniej'
    """

    con = mysql.connect() # łącze się z bazą danych
    cursor = con.cursor()
    cursor.callproc('sp_getTurniej', (id,)) # pobieram dane o podanym turnieju
    dane = cursor.fetchall()

    if session.get('user') == dane[0][5]: # sprawdzam czy zalogowany gracz jest nadzorcą tego turnieju
        cursor.callproc('sp_deleteTurniej',(id,)) # usuwanie turnieju z bazy wraz z jego meczami
        dane = cursor.fetchall()
        con.commit()
        cursor.close()
        con.close()
        return redirect('/myTournaments/0') # wyświetlenie strony z turniejami użytkownika
    else:
        con.commit()
        cursor.close()
        con.close()
        return redirect('/myTournaments/0')

@app.route('/rank')
def rank():
    """
    Metoda pobiera informacje o liczbie wygranych oraz przegranych meczy.
    Tworzy listę użytkowników wraz z tym informacjami oraz sortuje według: ilość_wygranych / ilość przegranych
    Korzysta z procedur w bazie danych: 'sp_getWinners' oraz 'sp_getLoosers'.
    """

    # łącze z bazą danych wywoluje procedury ktore wypisują informację o wygranych, przegranych meczach
    con = mysql.connect()
    cursor = con.cursor()
    cursor.callproc('sp_getWinners', )
    dane = cursor.fetchall()
    cursor.callproc('sp_getLoosers', )
    dane2 = cursor.fetchall()
    con.commit() # zamykam połączenie z bazą
    cursor.close()
    con.close()

    statystyki={} # słownik będzie zawierać dla każdego gracza jego statystyki
    tmp={}
    for i in dane2:
        tmp[i[0]] = i[1]
    for i in dane:
        statystyki[i[0]] = [i[1], tmp[i[0]]]

    for i in statystyki.copy():    #wyrzucam ze statystyk graczy, którzy nie rozegrali, żadnego meczu:
        if (statystyki[i][0] + statystyki[i][1]) == 0:
            statystyki.pop(i)


    # sortuje wyniki graczy od najlepszego według wartości: (wygrane_mecze / rozegrane_mecze)
    statystyki = OrderedDict(sorted(statystyki.items(), key=lambda x: (x[1][0]) / (x[1][0]+x[1][1]), reverse=True))


    if len(statystyki): # przekazanie danych do wyświetlenia rankingu
        return render_template('rank.html', statystyki=statystyki, login=session.get('user'))
    else:
        return render_template('info.html', info='brak danych', login=session.get('user'))

@app.route('/logout')
def logout():
    """
    Metoda służąca do wylogowania się użytkownika.
    """
    if session.get('user'):
        session.pop('user', None)
        return redirect('/')
    else:
        return redirect('/')


if __name__ == "__main__":
    app.run()


