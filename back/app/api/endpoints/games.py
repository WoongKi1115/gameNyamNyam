import requests
from recommend import recommend_game
from recommend import recommend_game_w2v
from dotenv import load_dotenv
import os
from fastapi import APIRouter
from db.Database import games
from schemas import game
from typing import List


router = APIRouter()

# env
load_dotenv()
steam_key = os.getenv('steam_key')


@router.get("/count/{steamId}")
async def get_game_count(steamId: str):
    """소유한 게임 개수 반환 함수.

    Input:
        steamId : 사용자 고유 식별번호.

    Output:
        소유한 게임 개수
    """
    url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={steam_key}&steamid={steamId}&format=json"
    response = requests.get(url)
    json_response = response.json()
    game_count = json_response["response"]["game_count"]
    return game_count


@router.post("/preference")
def get_preference(user_type: bool, steamId: str, table_list: List):
    """선호 장르 분석

    Input:
        user_type : 게임 기록이 5개 이상이면 True, 아니면 False
        steamId : 16자리 스팀 아이디
        table_list : 장바구니 게임 리스트

    Output:
        선호 장르 5개 리스트

    """
    playedGenres = []
    result = {}

    if(user_type):

        # 1. 플레이했던 게임 정보(appid) 불러오기
        appids = []
        playedGames = {}
        url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={steam_key}&steamid={steamId}"
        response = requests.get(url)
        json_response = response.json()
        playedGames = json_response["response"]["games"]

        for k in playedGames:
            appids.append(k['appid'])

        # 2. 불러온 appid를 이용해 db에서 game detail 가져오기
        for k in appids:
            playedGenres.append(games.find_one({"appid": str(k)}, {
                "_id": 0, "genres": 1}))

    else:
        # 1. 불러온 appid를 이용해 db에서 game detail 가져오기
        for k in table_list:
            playedGenres.append(games.find_one({"appid": k}, {
                "_id": 0, "genres": 1}))

    # 3. game detail list에서 장르 뽑아서 5개 가져오기
    result = recommend_game.get_preference(playedGenres)

    return result




@router.post("/result")
def get_rate(preference: List,
             table_list: List):
    """뽑은 게임 리스트에 대한 매치율 저장

    Input:
        games : 게임의 앱 아이디가 담긴 리스트
        preference : 선호 장르 리스트

    Output:
        비슷한 게임들의 앱아이디, 제목, 이미지
    """
    game_genres = []
    
    # DB 조회
    for appid in table_list:
        game_genres.append(games.find_one({"appid": appid}, {
                          "_id": 0, "appid": 1, "genres": 1}))

    result = recommend_game.get_rate(preference, game_genres)
    return result


@router.post("/similar", response_model=List[game.GameBase])
def get_similar_game(table_list: List):
    """비슷한 게임 추천.

    Input:
        games : 게임의 앱 아이디가 담긴 리스트

    Output:
        비슷한 게임들의 앱아이디, 제목, 이미지
    """
    appList = recommend_game_w2v.get_recommended_games(table_list)
    similar_game_list = games.find(
        { "appid": { "$in": appList, "$nin": table_list } },
        {"_id": 0, "appid": 1, "name": 1, "price": 1, "image": 1}
    )

    result = []

    for game in similar_game_list[:10]:
        result.append(game)

    return result


####################
# 게임 관련
####################

@router.post("/all/yes", response_description="구매 기록이 5개 이상인 유저의 게임 목록", response_model=List[game.GameBase])
def get_games_yes_data(steamId: str):
    """선호도에 게임 리스트 출력
    1) 이미 플레이한 게임은 나오지 않음.

    2) 게임 기록이 5개 이상 사용자
    → 총 60개 (사용자 정보 기반 추천 게임 30개, 무작위 15개, 인기순위 10개, 신규게임 5개)

    Input:
        steamId : 사용자 고유 식별 아이디

    Output:
        60개의 게임 리스트 (appid, image, name)
    """

    result = []
    already_selected = [] # 이미 플레이한 게임 담기

    # (1) 추천 게임 30개 가져오기

    res = requests.get(f'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={steam_key}&steamid={steamId}').json()
    game_cnt=res['response']['game_count']
    user_games = res['response']['games']
    owned_games = []
    for i in range(game_cnt):
        owned_games.append(str(user_games[i]["appid"]))
        already_selected.append(str(user_games[i]["appid"]))

    appList = recommend_game_w2v.get_recommended_games(owned_games)

    recommend_game_list = games.find(
        { "appid": { "$in": appList, "$nin": already_selected } },
        {"_id": 0, "appid": 1, "name": 1, "price": 1, "image": 1}
    )

    for game in recommend_game_list:
        result.append(game)   
        already_selected.append(game["appid"]) 

    # (2) 신규 게임 5개 가져오기
    latest_game = games.aggregate([
        { "$sort": { "release_date": -1 } },
        { "$match": { "appid": { "$nin": already_selected } } },
        { "$limit": 30 },
        { "$sample": { "size": 5 } },
        { "$project": { "_id": 0, "appid":1, "name": 1, "price": 1, "image": 1  } }
    ])

    for game in latest_game:
        result.append(game)
        already_selected.append(game["appid"])
    

    # (3) 무작위 15개 가져오기
    random_game_cur = games.aggregate([
        { "$match": { "appid": { "$nin": already_selected } } },
        { "$sample": { "size": 15 } },
        { "$project": { "_id": 0, "appid":1, "name": 1, "price": 1, "image": 1  } }
    ])

    for game in random_game_cur:
        result.append(game)
        already_selected.append(game["appid"])

    # (4) 인기순위 10개 가져오기
    popular_game_cur = games.aggregate([
        { "$sort": { "recommendations": -1 } },
        { "$match": { "appid": { "$nin": already_selected } } },
        { "$limit": 100 },
        { "$sample": { "size": 10 } },
        { "$project": { "_id": 0, "appid":1, "name": 1, "price": 1, "image": 1  } }
    ])
  
    for game in popular_game_cur:
        result.append(game)
        already_selected.append(game["appid"])

    # print(len(result))
    return result

@router.post("/all/no", response_description="구매 기록이 5개 미만인 유저의 게임 목록", response_model=List[game.GameBase])
def get_games_no_data():
    """선호도에 게임 리스트 출력
    1) 이미 플레이한 게임은 나오지 않음.

    2) 게임 기록이 5개 미만 사용자
    → 총 60개 (무작위 30개, 인기순위 25개, 신규게임 5개)

    Args:
        steamId : 사용자 고유 식별 아이디

    Returns:
        60개의 게임 리스트 (appid, image, name)
    """

    result = []
    already_selected = [] # 이미 플레이한 게임 담기

    # 신규 게임 5개 가져오기
    latest_game = games.aggregate([
        {"$sort": {"release_date": -1}},
        {"$match": {"appid": {"$nin": already_selected}}},
        {"$limit": 30},
        {"$sample": {"size": 5}},
        {"$project": {"_id": 0, "appid": 1, "name": 1, "price": 1, "image": 1}}
    ])

    for game in latest_game:
        result.append(game)
        already_selected.append(game["appid"])

    # 무작위 30개 가져오기
    random_game_cur = games.aggregate([
        {"$match": {"appid": {"$nin": already_selected}}},
        {"$sample": {"size": 30}},
        {"$project": {"_id": 0, "appid": 1, "name": 1, "price": 1, "image": 1}}
    ])

    for game in random_game_cur:
        result.append(game)
        already_selected.append(game["appid"])

    # 인기순위 25개 가져오기
    popular_game_cur = games.aggregate([
        {"$sort": {"recommendations": -1}},
        {"$match": {"appid": {"$nin": already_selected}}},
        {"$limit": 100},
        {"$sample": {"size": 25}},
        {"$project": {"_id": 0, "appid": 1, "name": 1, "price": 1, "image": 1}}
    ])

    for game in popular_game_cur:
        result.append(game)
        already_selected.append(game["appid"])

    
    #print(len(result))
    return result


@router.get("/detail/{appid}", response_description="Get a game detail", response_model=game.GameDetail)
def get_game_detail(appid: str):
    """게임 상세 정보 반환 함수.

    Args:
        appid : 게임의 앱 아이디

    Returns:
        제목, 가격, 스크린샷, 짧은 설명, 개발사, 출시일, 장르, 카테고리
    """
    # DB 조회
    result = games.find_one({"appid": appid}, {
        "_id": 0, "recommendations": 0, "metacritic": 0, "about_the_game": 0})

    # categories, genres, screenshots, developers 리스트화
    result["categories"] = result["categories"].split(",")

    # Steam이 포함된 카테고리는 제외.
    filtered_categories = []
    for category in result["categories"]:
        if "Steam" not in category:
            filtered_categories.append(category)
    result["categories"] = filtered_categories

    result["genres"] = result["genres"].split(",")
    result["screenshots"] = result["screenshots"].split(",")
    result["developers"] = result["developers"].split("///")

    return result
