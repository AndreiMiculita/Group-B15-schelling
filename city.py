import colorsys
import os
import random
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from agent import Agent, RealNumberFeature, BinaryFeature, CategoricalFeature, religion_preference_matrix
from home import Home
from landmark import Landmark, CategoricalFeature, religion_preference_matrix
from params import *
from cluster_counts import cluster_religion, cluster_ethnicity, income_comparison


def neighbors(a, radius, rowNumber, columnNumber, agent):
    """Get a list of all the neighbors
    :param a: city matrix
    :param radius: maximum chebyshev distance to check
    :param rowNumber: current row number of house
    :param columnNumber: current column number of house
    :param agent: agent living in house
    :return a list containing the neighbor agent objects"""
    house_neighbors = []

    # Add any neighbors in range thar are not the agent itself.
    for i in range(rowNumber - radius, rowNumber + radius + 1):
        for j in range(columnNumber - radius, columnNumber + radius + 1):
            if 0 <= i < len(a) and 0 <= j < len(a[0]):
                if not a[i][j].empty and a[i][j].occupant != agent:
                    house_neighbors.append(a[i][j].occupant)
    return house_neighbors


def neighbors_weighted(a, radius, rowNumber, columnNumber, agent):
    """Closer neighbors are more important (counted multiple times)
    :param a: city matrix
    :param radius: maximum chebyshev distance to check
    :param rowNumber: current row number of house
    :param columnNumber: current column number of house
    :param agent: agent living in house
    :return a list containing the neighbor agent objects"""
    house_neighbors = []

    # Add any neighbors in range that are not the agent itself.
    for r in range(1, radius + 1):
        for i in range(rowNumber - r, rowNumber + r + 1):
            for j in range(columnNumber - r, columnNumber + r + 1):
                if 0 <= i < len(a) and 0 <= j < len(a[0]):
                    if not a[i][j].empty and a[i][j].occupant != agent:
                        house_neighbors.append(a[i][j].occupant)
    return house_neighbors


def generate_city():
    """Generate a random city grid based on the parameters"""
    # City is a matrix with a padding
    grid = np.zeros((w + 2, h + 2), dtype=object)
    for x in range(-2, w + 2):
        for y in range(-2, h + 2):
            # These are 2 rows/columns that will not show in the bitmap,
            # but we will use them to generate the first row/column
            if x < 0 or y < 0 or x >= w or y >= h:
                price = random.randint(min_price, max_price)
            # Average some neighboring houses then add noise
            else:
                price = np.average([grid[x][y - 1].price, grid[x][y - 2].price,
                                    grid[x - 1][y].price, grid[x - 2][y].price,
                                    grid[x - 1][y + 1].price, grid[x - 2][y + 1].price])
                price = price + random.randint(-price_noise * max_price, price_noise * max_price)

                # Noise may have made price above max, limit it to the [0, max_price] interval
                if price > max_price:
                    price = max_price
                elif price < 0:
                    price = 0

            # Move all values toward 0 and max_price a bit, depending on which they are closer to
            # Do a weighted average - price_segregation is the weight of the endpoints
            if price < max_price / 2:
                price = price / (1 + price_segregation)
            else:
                price = (price + max_price * price_segregation) / (1 + price_segregation)

            # 1 in 10 probability of an empty house, 1 in 100 for a landmark. Landmark takes priority over empty
            empty = random.randint(1, 1 / empty_ratio) == 1
            landmark = random.randint(1, 1 / landmark_ratio) == 1
            if landmark:
                empty = 0

            # If both empty and landmark are false, make an agent
            if not empty or not landmark:
                # Creating a random agent that lives in that home
                eth = (random.randint(1, 2) == 1)
                a = Agent(religion=CategoricalFeature(value=random.randint(1, 5),
                                                      preference_matrix=religion_preference_matrix),
                          ethnicity=BinaryFeature(value=eth),
                          income=RealNumberFeature(value=random.randint(min_income, max_income), threshold=30000),
                          landmark=0,
                          weights=weight_list)
            # If empty is true, make the space empty
            elif empty:
                a = None
            # Lastly if not empty and landmark is true, make a landmark of a random religion
            if landmark:
                a = Landmark(religion=CategoricalFeature(value=random.randint(1, 5),
                                                         preference_matrix=religion_preference_matrix),
                             landmark=1)

            # Generating a home with a price depending on its location
            grid[x][y] = Home(price=price, empty=empty, landmark=landmark, occupant=a)
    return grid


def time_step(i):
    """Makes one time step (epoch) pass
    :param i: the number of the time step
    :return ratio of agents that are satisfied at the end of the time step"""
    # A print showing the progress of the iterations, helpful to see progress is being made while simulating.
    if i % 2 == 0:
        print(i)

    city_satisfactions = []
    # Go through the entire city to check whether occupants are satisfied
    for (x, y), house in np.ndenumerate(city):
        # Skip edge for now
        if not (house.empty or house.landmark):
            agent = house.occupant
            house_neighbors = neighbors(city, radius, x, y, agent)
            satisfaction = agent.satisfied(house_neighbors)
            city_satisfactions.append(int(satisfaction > 0.5))
            # If the agent is not satisfied with their current position, try to move
            if not satisfaction > 0.5:
                # Move the agent to a random empty house that they are satisfied with
                # first build a list of prospects
                prospects = []
                # Move as soon as prospect is filled
                for (xm, ym), housem in np.ndenumerate(city):
                    if housem.empty:
                        # In some cases we want them to not check the future home, and move randomly
                        if not check_future_home:
                            prospects.append((xm, ym))
                        else:
                            # checking if prospect is satisfying
                            p_house_neighbors = neighbors(city, radius, xm, ym, agent)
                            if agent.satisfied(p_house_neighbors) > 0.5:
                                prospects.append((xm, ym))
                                break
                if prospects:  # if list is not empty, move to a random element
                    target_house = city[random.choice(prospects)]
                    target_house.occupant = house.occupant
                    target_house.empty = False
                    house.occupant = None
                    house.empty = True

    return np.average(city_satisfactions)


def get_frame(city):
    """Draw the city
    :param city: the city grid
    :return tuple of religion, ethnicity and income images"""
    data = np.zeros((h + 1, w + 1, 3), dtype=np.uint8)

    # Plot incomes
    for (x, y), house in np.ndenumerate(city):
        if x > w or y > h:
            continue
        if not (house.empty or house.landmark):
            # equation of a line through 2 points (min_income, 0) and (max_income,255)
            color = int((house.occupant.income.value - min_income) * 255 / (max_income - min_income))
            plt.scatter(x, y, c='#%02x%02x%02x' % (255, color, 255),s=100)
            data[x][y] = [color, 255, color]
        elif house.landmark:
            # Make landmarks green on the income map
            plt.scatter(x,y,c="green",s=100,marker="^")
        else:
            # Show Empty spaces as black on the income map
            plt.scatter(x,y,c="black",s=100)

    plt.gca().set_aspect('equal', adjustable='box')
    plt.axis("off")

    canvas = plt.get_current_fig_manager().canvas
    canvas.draw()
    img_income = Image.frombytes('RGB', canvas.get_width_height(), canvas.tostring_rgb())

    # Plot ethnicities
    for (x, y), house in np.ndenumerate(city):
        if x > w or y > h:
            continue
        if not (house.empty or house.landmark):
            # Since ethnicity is binary for now, add fixed colors red and blue based on ethnicity value
            if house.occupant.ethnicity.value:
                plt.scatter(x, y, c="red",s=100)
            else:
                plt.scatter(x,y,c="blue",s=100)
        elif house.landmark:
            # Make landmarks green on the ethnicity map
            plt.scatter(x,y,c="green",s=100,marker="^")
        else:
            # Show empty spaces as black on the ethnicity map
            plt.scatter(x,y,c="black",s=100)

    plt.gca().set_aspect('equal', adjustable='box')
    plt.axis("off")

    canvas = plt.get_current_fig_manager().canvas
    canvas.draw()
    img_ethnicity = Image.frombytes('RGB', canvas.get_width_height(), canvas.tostring_rgb())

    # Plot religions
    total_religions = 5
    for (x, y), house in np.ndenumerate(city):
        if x > w or y > h:
            continue
        if not house.empty:
            # Add a unique color for every religion
            this_religion = house.occupant.religion.value
            rc, gc, bc = colorsys.hls_to_rgb(this_religion / total_religions, 0.4, 1)
            rgb_255 = (int(rc * 255), int(gc * 255), int(bc * 255))
            if not house.landmark:
                # Give the agents the color of their religion on the religion map
                plt.scatter(x, y, c='#%02x%02x%02x' % rgb_255, s=100)
            else:
                # Give landmarks the color of their religion on the religion map, and make them a triangle
                plt.scatter(x, y, c='#%02x%02x%02x' % rgb_255, s=100, marker="^")
        else:
            plt.scatter(x, y, c="black", s=100)
    plt.gca().set_aspect('equal', adjustable='box')
    plt.axis("off")

    canvas = plt.get_current_fig_manager().canvas
    canvas.draw()
    img_religion = Image.frombytes('RGB', canvas.get_width_height(), canvas.tostring_rgb())

    return img_religion, img_ethnicity, img_income


if __name__ == "__main__":
    city = generate_city()

    cluster_religion(city)
    cluster_ethnicity(city)
    outpath = "out_" + str(w) + "x" + str(h) + "_r" + str(radius) + "_weights" + str(weight_list[0]) + str(weight_list[1]) + str(weight_list[2])
    os.makedirs(outpath, exist_ok=True)

    # Bitmap for the gifs
    data = np.zeros((h + 1, w + 1, 3), dtype=np.uint8)

    # Plot house prices
    # House prices are currently not used in our final version, however they are generated and
    # could be used for future projects.
    for (x, y), house in np.ndenumerate(city):
        if x > w or y > h:
            continue
        if not (house.empty or house.landmark):
            color = house.price / max_price * 255
            data[x][y] = [255, color, color]
        elif house.landmark:
            data[x][y] = [255, 255, 0]
        else:
            data[x][y] = [0, 0, 0]

    img = Image.fromarray(data, 'RGB')

    # Upscale image so it's easier to see
    img = img.resize((int(w * zoom), int(h * zoom)), Image.NEAREST)
    img.save(outpath + "/house_prices.png")

    avg_satisfaction_over_time = []

    frames_religion = []
    frames_ethnicity = []
    frames_income = []
    cluster_eth =[]
    cluster_rel = []
    inc_satisfaction = []
    # Go up to max_iterations, reaching max iterations is a terminating condition
    for i in range(0, max_iterations):
        frame_religion, frame_ethnicity, frame_income = get_frame(city)
        frames_religion.append(frame_religion)
        frames_ethnicity.append(frame_ethnicity)
        frames_income.append(frame_income)
        inc_satisfaction.append(income_comparison(city))
        e_c, e_s = cluster_ethnicity(city)
        r_c, r_s = cluster_religion(city)
        cluster_eth.append(e_c)
        cluster_rel.append(r_c)
        avg_satisfaction = time_step(i)
        # If the average satisfaction reaches the threshold, trigger the second possible terminating condition
        if avg_satisfaction > satisfaction_threshold:
            break

        avg_satisfaction_over_time.append(avg_satisfaction)

    # Satisfaction over time plot
    plt.clf()
    plt.plot(avg_satisfaction_over_time)
    plt.title("Average Satisfaction Over Time")
    plt.xlabel("Number of Steps")
    plt.ylabel("Average Satisfaction of all Agents")
    plt.xlim(xmin=0)
    plt.ylim(ymin=0)
    plt.savefig(outpath + "/avg_satisfaction.png")
    print(f"average satisfaction: {avg_satisfaction}")

    frames_ethnicity[0].save(outpath + "/ethnicities.gif", append_images=frames_ethnicity[1:], save_all=True, duration=200,
                             loop=1)
    frames_income[0].save(outpath + "/income.gif", append_images=frames_income[1:], save_all=True, duration=200, loop=1)
    frames_religion[0].save(outpath + "/religion.gif", append_images=frames_religion[1:], save_all=True, duration=200, loop=1)
    
    # Ethnicity cluster plot
    plt.clf()
    plt.plot(cluster_eth)
    plt.title("Cluster Count Over Time for Ethnicity")
    plt.xlabel("Number of Steps")
    plt.ylabel("Number of Clusters")
    plt.savefig(outpath + "/cluster_count_ethnicity.png")
    
    # Religion cluster plot
    plt.clf()
    plt.plot(cluster_rel)
    plt.title("Cluster Count Over Time for Religion")
    plt.xlabel("Number of Steps")
    plt.ylabel("Number of Clusters")
    plt.xlim(xmin=0)
    plt.ylim(ymin=0)
    plt.savefig(outpath + "/cluster_count_religion.png")

    # Income satisfaction plot
    plt.clf()
    plt.plot(inc_satisfaction)
    plt.title("Neighbor Income Satisfaction over Time")
    plt.xlabel("Number of Steps")
    plt.ylabel("Average Satisfaction regarding Neighbor Incomes")
    plt.xlim(xmin=0)
    plt.ylim(ymin=0)
    plt.savefig(outpath + "/income_satisfaction.png")

    # Combined cluster
    plt.clf()
    plt.plot(cluster_rel, label='Religion')
    plt.plot(cluster_eth, label='Ethnicity')
    plt.title("Cluster Count Over Time")
    plt.xlabel("Number of Steps")
    plt.ylabel("Number of Clusters")
    plt.legend(loc='upper right')
    plt.xlim(xmin=0)
    plt.ylim(ymin=0)
    plt.savefig(outpath + "/cluster_rel_eth.png")

    # Print final clusters
    print("last clusters")
    print("religion")
    cluster_religion(city)
    print("ethnicity")
    cluster_ethnicity(city)

    print('INCOME Satisfaction')
    print(inc_satisfaction[0],inc_satisfaction[-1])

    print('Cluster Counts')
    print('Ethnicity')
    print(cluster_eth[0], cluster_eth[-1])
    print('Religion')
    print(cluster_rel[0], cluster_rel[-1])
