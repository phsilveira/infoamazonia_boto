document.addEventListener('DOMContentLoaded', function() {
    // User Engagement Chart
    const engagementChart = document.getElementById('engagementChart');
    if (engagementChart) {
        const engagementCtx = engagementChart.getContext('2d');
        new Chart(engagementCtx, {
            type: 'line',
            data: {
                labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                datasets: [{
                    label: 'Active Users',
                    data: [120, 190, 300, 250, 400, 380],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top',
                    }
                }
            }
        });
    }

    // Message Statistics Chart
    const messageChart = document.getElementById('messageChart');
    if (messageChart) {
        const messageCtx = messageChart.getContext('2d');
        new Chart(messageCtx, {
            type: 'bar',
            data: {
                labels: ['Sent', 'Received', 'Read', 'Clicked'],
                datasets: [{
                    label: 'Message Statistics',
                    data: [1200, 1000, 800, 400],
                    backgroundColor: [
                        'rgba(54, 162, 235, 0.5)',
                        'rgba(75, 192, 192, 0.5)',
                        'rgba(255, 206, 86, 0.5)',
                        'rgba(255, 99, 132, 0.5)'
                    ],
                    borderColor: [
                        'rgba(54, 162, 235, 1)',
                        'rgba(75, 192, 192, 1)',
                        'rgba(255, 206, 86, 1)',
                        'rgba(255, 99, 132, 1)'
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // Articles Statistics Chart
    const articlesChart = document.getElementById('articlesChart');
    if (articlesChart) {
        const articlesCtx = articlesChart.getContext('2d');
        
        // Use fetch to get real data for the chart
        fetch('/api/article-stats')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Create the chart with real data
                    new Chart(articlesCtx, {
                        type: 'bar',
                        data: {
                            labels: ['Total Articles'],
                            datasets: [{
                                label: 'Article Count',
                                data: [data.stats.total_count],
                                backgroundColor: 'rgba(75, 192, 192, 0.5)',
                                borderColor: 'rgba(75, 192, 192, 1)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: {
                                y: {
                                    beginAtZero: true
                                }
                            }
                        }
                    });
                }
            })
            .catch(error => {
                console.error('Error fetching article stats for chart:', error);
            });
    }
});
